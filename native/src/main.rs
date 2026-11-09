//! Native standalone Windows TeamSpeak engine for Teamspeak Heerlen PC.
//! Uses the SAME Rust tslib-core + tslib-audio lineage as the Android version.
//! Communicates with the Python desktop UI over newline-delimited JSON pipes.
//! User secrets are not printed to stdout. All server traffic goes directly to TS.
use anyhow::{Context, Result};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
mod microphone;
mod speaker;
use std::f32::consts::PI;
use std::io::{self, BufRead, Write};
use std::path::PathBuf;
use std::time::{Duration, Instant};
use tokio::sync::mpsc;
use tslib_audio::codec::{Decoder, Encoder, OpusCodec, OpusDecoder};
use tslib_audio::AudioConfig;
use tslib_core::{Client, ClientConfig, Event, Identity};
use tslib_core::events::AudioCodec;

const HOST: &str = "heerlen.mijnts3.nl";

fn emit(value: Value) {
    println!("{}", value);
    let _ = io::stdout().flush();
}

fn notice(message: impl AsRef<str>) {
    emit(json!({"type": "notice", "message": message.as_ref()}));
}

fn main() {
    if let Err(err) = run_main() {
        emit(json!({"type": "error", "message": err.to_string()}));
        std::process::exit(1);
    }
}

#[tokio::main(flavor = "current_thread")]
async fn run_main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) == Some("--list-microphones") {
        emit(json!({"type": "devices", "microphones": microphone::available()}));
        return Ok(());
    }
    let nickname = args.get(1).context("Gebruikersnaam ontbreekt")?.trim();
    let identity_file = args.get(2).context("Identiteitsbestand ontbreekt")?;
    let requested_mic = args.get(3).map(String::as_str).unwrap_or(microphone::DEFAULT_MIC);
    if nickname.chars().count() < 3 || nickname.chars().count() > 30 ||
       nickname.chars().any(|ch| ch.is_control()) {
        anyhow::bail!("Gebruikersnaam moet 3 tot 30 gewone tekens bevatten");
    }
    let identity_path = PathBuf::from(identity_file);
    if let Some(parent) = identity_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut identity = if identity_path.exists() {
        Identity::load(&identity_path).context("Opgeslagen identiteit lezen mislukt")?
    } else {
        let generated = Identity::create()?;
        generated.save(&identity_path).context("Identiteit opslaan mislukt")?;
        generated
    };
    if identity.security_level() < 8 {
        notice("Eerste start: TeamSpeak-identiteit voorbereiden (beveiligingsniveau 8)...");
        identity.improve(8).context("TeamSpeak-identiteit verbeteren mislukt")?;
        identity.save(&identity_path).context("TeamSpeak-identiteit bewaren mislukt")?;
    }
    identity.set_nickname(nickname.to_string());
    let config = ClientConfig::builder()
        .address(HOST)
        .identity(identity)
        .nickname(nickname)
        .build()?;
    notice(format!("Direct verbinden met {} als {}...", HOST, nickname));
    let mut client = Client::connect(config).context("Kan server niet bereiken")?;
    client.wait_connected().await.context("TeamSpeak-verbinding geweigerd")?;
    if let Err(err) = client.set_input_muted(true) {
        notice(format!("Microfoon dempen bij opstarten niet beschikbaar: {}", err));
        // No audio packets are sent until explicit PTT, so this is safe.
    }

    let mut audio_config = AudioConfig::default();
    audio_config.vad_enabled = false; // transmit only while PTT is pressed
    // Windows output is also independent of TeamSpeak networking. Use
    // the system's actual supported rate/channels rather than 48k mono.
    let speaker = match speaker::open() {
        Ok(value) => {
            notice(format!("Windows luidspreker gereed: {} ({})", value.name, value.format));
            Some(value)
        }
        Err(err) => {
            notice(format!("TeamSpeak blijft verbonden, maar luidspreker niet beschikbaar: {}", err));
            None
        }
    };
    let playback_ready = speaker.is_some();
    let mut decoders = HashMap::<(u16, u8), OpusDecoder>::new();
    let (frame_tx, mut audio_rx) = mpsc::channel::<Vec<i16>>(48);
    let microphone = match microphone::open(requested_mic, frame_tx) {
        Ok(mic) => {
            notice(format!("Windows microfoon gevonden: {} ({})", mic.name, mic.format));
            Some(mic)
        }
        Err(err) => {
            notice(format!("TeamSpeak blijft verbonden, maar microfoon niet beschikbaar: {}. Selecteer een andere microfoon bij Instellingen.", err));
            None
        }
    };
    let mut mic_encoder = OpusCodec::new(audio_config.clone())?.create_encoder()?;
    let mut encoded_frame = vec![0_u8; 4000];
    emit(json!({
        "type": "audio_status", "mic_ready": microphone.is_some(),
        "mic_name": microphone.as_ref().map(|m| m.name.as_str()).unwrap_or("Geen microfoon"),
        "output_ready": playback_ready,
    }));
    emit(json!({"type": "notice", "message": "Zelfstandig verbonden. PTT is klaar zodra de microfoon beschikbaar is."}));

    let (cmd_tx, mut commands) = mpsc::unbounded_channel::<Value>();
    std::thread::spawn(move || {
        let input = io::stdin();
        for line in input.lock().lines() {
            match line {
                Ok(line) => {
                    if let Ok(command) = serde_json::from_str::<Value>(&line) {
                        if cmd_tx.send(command).is_err() { break; }
                    }
                },
                Err(_) => break,
            }
        }
        let _ = cmd_tx.send(json!({"action": "disconnect"}));
    });

    let mut tx = false;
    let mut roger = false;
    let mut speaking = HashSet::<u16>::new();
    let mut next_snapshot = Instant::now();
    let mut running = true;
    while running {
        while let Ok(command) = commands.try_recv() {
            let action = command["action"].as_str().unwrap_or("");
            match action {
                "ptt_on" => {
                    if microphone.is_none() {
                        notice("PTT niet beschikbaar: geen microfoon. De serververbinding blijft actief.");
                    } else if !tx {
                        if let Err(err) = client.set_input_muted(false) {
                            notice(format!("Microfoon kon niet aan: {}", err));
                        } else {
                            tx = true;
                        }
                    }
                },
                "ptt_off" => {
                    if tx {
                        tx = false;
                        if roger {
                            if let Err(err) = send_roger(&mut client, &audio_config).await {
                                notice(format!("Rogerpiep mislukt: {}", err));
                            }
                        }
                        if let Err(err) = client.set_input_muted(true) {
                            notice(format!("Microfoon dempen mislukt: {}", err));
                        }
                    }
                },
                "roger" => roger = command["enabled"].as_bool().unwrap_or(false),
                "join" => {
                    if let Some(cid) = command["cid"].as_u64() {
                        if let Err(err) = client.move_to_channel(cid) {
                            notice(format!("Kanaalwissel geweigerd: {}", err));
                        }
                    }
                },
                "chat" => {
                    if let Some(msg) = command["text"].as_str() {
                        let msg = msg.trim();
                        if !msg.is_empty() && msg.chars().count() <= 1000 {
                            if let Err(err) = client.send_channel_message(msg) {
                                notice(format!("Bericht mislukt: {}", err));
                            }
                        }
                    }
                },
                "disconnect" => running = false,
                _ => {},
            }
        }

        // Poll the full TeamSpeak protocol. Unlike ClientQuery this is real
        // server communication, including incoming Opus packets.
        for event in client.wait_events(10).await? {
            match event {
                Event::AudioReceived { user_id, data, codec, .. } => {
                    let codec_id = codec.id();
                    if let Some(output) = &speaker {
                        if codec_id == 4 || codec_id == 5 {
                            let key = (user_id, codec_id);
                            let channels: u16 = if codec_id == 5 { 2 } else { 1 };
                            if !decoders.contains_key(&key) {
                                let audio_spec = AudioConfig {
                                    channels,
                                    ..AudioConfig::default()
                                };
                                match OpusCodec::new(audio_spec).and_then(|c| c.create_decoder()) {
                                    Ok(decoder) => { decoders.insert(key, decoder); }
                                    Err(err) => notice(format!("Opus-decoder niet beschikbaar: {}", err)),
                                }
                            }
                            if let Some(decoder) = decoders.get_mut(&key) {
                                let mut raw = vec![0_i16; 5760 * channels as usize];
                                match decoder.decode(&data, &mut raw) {
                                    Ok(len) => {
                                        if channels == 1 {
                                            output.push(&raw[..len]);
                                        } else {
                                            let mono: Vec<i16> = raw[..len].chunks_exact(2)
                                                .map(|pair| ((pair[0] as i32 + pair[1] as i32) / 2) as i16)
                                                .collect();
                                            output.push(&mono);
                                        }
                                    }
                                    Err(err) => notice(format!("Opus ontvangen audio fout: {}", err)),
                                }
                            }
                        }
                    }
                },
                Event::TalkStatusStart { user_id, .. } => { speaking.insert(user_id); },
                Event::TalkStatusStop { user_id } => { speaking.remove(&user_id); },
                Event::UserLeft { user, .. } => {
                    speaking.remove(&user.id);
                    decoders.retain(|(uid, _), _| *uid != user.id);
                },
                Event::TextMessage { sender_name, message, .. } => {
                    emit(json!({"type": "chat", "message": format!("{}: {}", sender_name, message)}));
                },
                Event::Disconnected { reason } | Event::ConnectionLost { reason } => {
                    notice(format!("TeamSpeak heeft verbinding verbroken: {}", reason));
                    running = false;
                },
                Event::CommandError { message, .. } => notice(message),
                _ => {},
            }
        }
        // The Windows capture callback supplies 48 kHz mono PCM in 20-ms
        // frames, adapting 44.1-kHz/stereo/i16/u16 devices automatically.
        // Raw PCM is discarded until PTT is actually pressed.
        while let Ok(pcm) = audio_rx.try_recv() {
            if tx {
                match mic_encoder.encode(&pcm, &mut encoded_frame) {
                    Ok(len) => {
                        if let Err(err) = client.send_audio(&encoded_frame[..len], AudioCodec::OpusVoice) {
                            notice(format!("Zenden mislukt: {}", err));
                        }
                    }
                    Err(err) => notice(format!("Microfoon-Opus fout: {}", err)),
                }
            }
        }
        if Instant::now() >= next_snapshot {
            snapshot(&client, &speaking, microphone.as_ref(), playback_ready);
            next_snapshot = Instant::now() + Duration::from_millis(650);
        }
        tokio::time::sleep(Duration::from_millis(4)).await;
    }
    // Always stop microphone transmission, even on graceful shutdown.
    let _ = client.set_input_muted(true);
    let _ = client.disconnect();
    emit(json!({"type": "closed"}));
    Ok(())
}

fn snapshot(client: &Client, talking: &HashSet<u16>, microphone: Option<&microphone::InputStream>, output_ready: bool) {
    let users = client.users();
    let channels = client.channels();
    let my_id = client.client_id().unwrap_or(0);
    let own_channel = client.channel_id().unwrap_or(0);
    let server = client.server_info().name;
    emit(json!({
        "type": "snapshot",
        "connected": client.is_connected(),
        "mic_ready": microphone.is_some(),
        "mic_name": microphone.map(|m| m.name.as_str()).unwrap_or("Geen microfoon"),
        "output_ready": output_ready,
        "server_name": server,
        "channel_id": own_channel,
        "my_id": my_id,
        "channels": channels.iter().map(|c| json!({
            "cid": c.id.to_string(), "pid": c.parent_id.to_string(),
            "channel_name": c.name, "channel_order": c.order.to_string(),
        })).collect::<Vec<_>>(),
        "users": users.iter().filter(|u| u.client_type == 0).map(|u| json!({
            "clid": u.id.to_string(), "cid": u.channel_id.to_string(),
            "client_nickname": u.nickname, "client_type": "0",
            "client_input_muted": if u.is_input_muted {"1"} else {"0"},
        })).collect::<Vec<_>>(),
        "talking": talking.iter().copied().collect::<Vec<_>>(),
    }));
}

/// Play 3 distinct remote-audible tones over the same Opus voice channel.
/// Kept unmuted until the last packet has been sent. On-air time ≈ 360 ms.
async fn send_roger(client: &mut Client, config: &AudioConfig) -> Result<()> {
    let codec = OpusCodec::new(config.clone())?;
    let mut encoder = codec.create_encoder()?;
    let mut packet = vec![0_u8; 4000];
    let sample_rate = config.sample_rate as f32;
    let samples_per_frame = config.frame_size_samples();
    let frequencies: [f32; 3] = [740.0, 980.0, 1240.0];
    let frames_per_tone = 6; // 6 x 20 ms
    for &freq in &frequencies {
        for frame in 0..frames_per_tone {
            let mut pcm = Vec::with_capacity(samples_per_frame);
            for n in 0..samples_per_frame {
                let i = frame * samples_per_frame + n;
                let phase = 2.0 * PI * freq * (i as f32) / sample_rate;
                let total = frames_per_tone * samples_per_frame;
                let envelope = ((i.min(total - 1 - i) as f32) / (sample_rate * 0.01)).min(1.0);
                pcm.push((phase.sin() * envelope.max(0.0) * 9500.0) as i16);
            }
            let len = encoder.encode(&pcm, &mut packet)?;
            client.send_audio(&packet[..len], AudioCodec::OpusVoice)?;
            tokio::time::sleep(Duration::from_millis(config.frame_size_ms as u64)).await;
        }
    }
    Ok(())
}
