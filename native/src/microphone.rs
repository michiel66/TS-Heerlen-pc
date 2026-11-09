//! Windows microphone capture using each device's supported native sample format.
//! The earlier tslib-audio capture path forced 48 kHz, mono, f32, which many
//! Windows microphones do not expose. Resample/downmix to 48 kHz mono here
//! before feeding the existing TeamSpeak Opus encoder.
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, SampleFormat, Stream, StreamConfig};
use std::sync::{Arc, Mutex};
use tokio::sync::mpsc;

pub const DEFAULT_MIC: &str = "Standaard (Windows)";
const CODEC_RATE: f64 = 48_000.0;
const FRAME_SAMPLES: usize = 960;

pub struct InputStream {
    // Keep the PortAudio/WASAPI stream alive for the duration of the session.
    _stream: Stream,
    pub name: String,
    pub format: String,
}

#[derive(Debug)]
struct FrameBuilder {
    last: f32,
    phase: f64,
    ratio: f64,
    frame: Vec<i16>,
}

impl FrameBuilder {
    fn new(input_rate: u32) -> Self {
        Self {
            last: 0.0, phase: 0.0, ratio: CODEC_RATE / input_rate as f64,
            frame: Vec::with_capacity(FRAME_SAMPLES),
        }
    }
    fn put(&mut self, mono: f32, tx: &mpsc::Sender<Vec<i16>>) {
        self.phase += self.ratio;
        while self.phase >= 1.0 {
            self.phase -= 1.0;
            // Interpolate when the device doesn't run at 48 kHz.
            let blend = (1.0 - self.phase / self.ratio).clamp(0.0, 1.0) as f32;
            let sample = (self.last + (mono - self.last) * blend).clamp(-1.0, 1.0);
            self.frame.push((sample * 32767.0) as i16);
            if self.frame.len() == FRAME_SAMPLES {
                let packet = std::mem::replace(&mut self.frame, Vec::with_capacity(FRAME_SAMPLES));
                // Never block the Windows audio callback if the UI/network lags.
                let _ = tx.try_send(packet);
            }
        }
        self.last = mono;
    }
}

fn process<T: Copy>(
    input: &[T],
    channels: usize,
    convert: fn(T) -> f32,
    state: &Arc<Mutex<FrameBuilder>>,
    tx: &mpsc::Sender<Vec<i16>>,
) {
    if let Ok(mut builder) = state.try_lock() {
        for frame in input.chunks_exact(channels.max(1)) {
            let summed = frame.iter().map(|v| convert(*v)).sum::<f32>();
            builder.put(summed / channels.max(1) as f32, tx);
        }
    }
}

pub fn available() -> Vec<String> {
    let host = cpal::default_host();
    let mut result = vec![DEFAULT_MIC.to_string()];
    if let Ok(devices) = host.input_devices() {
        for d in devices {
            if let Ok(name) = d.name() {
                if !result.contains(&name) { result.push(name); }
            }
        }
    }
    result
}

fn candidates(chosen: &str) -> Vec<Device> {
    let host = cpal::default_host();
    let mut devices = Vec::new();
    if chosen != DEFAULT_MIC && !chosen.is_empty() {
        if let Ok(inputs) = host.input_devices() {
            for d in inputs {
                if d.name().ok().as_deref() == Some(chosen) {
                    devices.push(d);
                    break;
                }
            }
        }
    }
    if let Some(default) = host.default_input_device() {
        devices.push(default);
    }
    if let Ok(inputs) = host.input_devices() {
        devices.extend(inputs);
    }
    devices
}

fn open_one(device: &Device, tx: mpsc::Sender<Vec<i16>>) -> Result<InputStream, String> {
    let selected = device.default_input_config()
        .map_err(|e| format!("Audioformaat opvragen: {}", e))?;
    let format = selected.sample_format();
    let config: StreamConfig = selected.config();
    let channels = config.channels as usize;
    let frame_builder = Arc::new(Mutex::new(FrameBuilder::new(config.sample_rate.0)));
    let microphone_name = device.name().unwrap_or_else(|_| "Microfoon".into());
    let description = format!("{} Hz, {} kanalen, {:?}", config.sample_rate.0, channels, format);
    let error_cb = move |err| eprintln!("Windows microfoon streamfout: {}", err);

    let stream = match format {
        SampleFormat::F32 => {
            let frames = frame_builder.clone();
            device.build_input_stream(
                &config,
                move |data: &[f32], _| process(data, channels, |s| s, &frames, &tx),
                error_cb, None
            )
        }
        SampleFormat::I16 => {
            let frames = frame_builder.clone();
            device.build_input_stream(
                &config,
                move |data: &[i16], _| process(data, channels, |s| s as f32 / 32768.0, &frames, &tx),
                error_cb, None
            )
        }
        SampleFormat::U16 => {
            let frames = frame_builder.clone();
            device.build_input_stream(
                &config,
                move |data: &[u16], _| process(data, channels, |s| (s as f32 - 32768.0) / 32768.0, &frames, &tx),
                error_cb, None
            )
        }
        _ => return Err(format!("Microfoon gebruikt nog niet ondersteund audioformaat {:?}", format)),
    }.map_err(|e| format!("Audio stream openen: {}", e))?;
    stream.play().map_err(|e| format!("Microfoon activeren: {}", e))?;
    Ok(InputStream { _stream: stream, name: microphone_name, format: description })
}

pub fn open(chosen: &str, tx: mpsc::Sender<Vec<i16>>) -> Result<InputStream, String> {
    let mut failures = Vec::new();
    let mut seen = Vec::new();
    for device in candidates(chosen) {
        let name = device.name().unwrap_or_else(|_| "Onbekend".into());
        if seen.contains(&name) { continue; }
        seen.push(name.clone());
        match open_one(&device, tx.clone()) {
            Ok(mic) => return Ok(mic),
            Err(error) => failures.push(format!("{}: {}", name, error)),
        }
    }
    Err(if failures.is_empty() {
        "Windows heeft geen beschikbare opnamemicrofoon gevonden. Controleer Instellingen > Privacy > Microfoon en de standaard invoer.".to_owned()
    } else {
        format!("Geen microfoon geopend. {}", failures.join(" | "))
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn converts_44100_stereo_to_48000_mono_frames() {
        let (sender, mut receiver) = mpsc::channel(16);
        let state = Arc::new(Mutex::new(FrameBuilder::new(44100)));
        let input = vec![0.2_f32; 44100 / 10 * 2]; // 0.1 sec stereo input
        process(&input, 2, |s| s, &state, &sender);
        let mut got = 0;
        while let Ok(frame) = receiver.try_recv() {
            got += 1;
            assert_eq!(frame.len(), 960);
        }
        assert_eq!(got, 5);
    }
    #[test]
    fn native_48000_mono_is_1_to_1() {
        let (sender, mut receiver) = mpsc::channel(2);
        let state = Arc::new(Mutex::new(FrameBuilder::new(48000)));
        process(&vec![0.1_f32; 960], 1, |s| s, &state, &sender);
        assert_eq!(receiver.try_recv().unwrap().len(), 960);
    }
}
