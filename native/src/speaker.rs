//! Windows output engine using the speaker's actual supported format.
//! The old tslib playback forced 48 kHz mono/f32, which could fail on stereo
//! headsets. This output opens the default system format and adapts mono PCM.
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, SampleFormat, Stream, StreamConfig};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

const OPUS_HZ: f64 = 48000.0;
const MAX_QUEUE: usize = 48000; // One second maximum to prevent lag buildup.

struct OutputFrames {
    samples: VecDeque<i16>,
    phase: f64,
    current: i16,
}
impl OutputFrames {
    fn new() -> Self {
        Self { samples: VecDeque::new(), phase: 0.0, current: 0 }
    }
    fn add(&mut self, data: &[i16]) {
        if self.samples.len() + data.len() > MAX_QUEUE {
            let remove = (self.samples.len() + data.len()).saturating_sub(MAX_QUEUE / 2);
            for _ in 0..remove.min(self.samples.len()) { self.samples.pop_front(); }
        }
        self.samples.extend(data.iter().copied());
    }
    fn next(&mut self, output_rate: f64) -> f32 {
        self.phase += OPUS_HZ / output_rate;
        while self.phase >= 1.0 {
            self.current = self.samples.pop_front().unwrap_or(0);
            self.phase -= 1.0;
        }
        self.current as f32 / 32768.0
    }
}

pub struct Speaker {
    _stream: Stream,
    pub name: String,
    pub format: String,
    frames: Arc<Mutex<OutputFrames>>,
}

impl Speaker {
    pub fn push(&self, samples: &[i16]) {
        if let Ok(mut buffer) = self.frames.lock() {
            buffer.add(samples);
        }
    }
}

fn fill<T: Copy>(output: &mut [T], channels: usize, rate: f64,
                 shared: &Arc<Mutex<OutputFrames>>, convert: fn(f32) -> T) {
    if let Ok(mut frames) = shared.try_lock() {
        for slice in output.chunks_mut(channels.max(1)) {
            let mono = frames.next(rate).clamp(-1.0, 1.0);
            for sample in slice.iter_mut() {
                *sample = convert(mono);
            }
        }
    } else {
        for sample in output.iter_mut() {
            *sample = convert(0.0);
        }
    }
}

fn start_one(device: &Device) -> Result<Speaker, String> {
    let supported = device.default_output_config()
        .map_err(|e| format!("Audioformat opvragen: {}", e))?;
    let format = supported.sample_format();
    let config: StreamConfig = supported.config();
    let channels = config.channels as usize;
    let rate = config.sample_rate.0 as f64;
    let name = device.name().unwrap_or_else(|_| "Windows-luidspreker".into());
    let shared = Arc::new(Mutex::new(OutputFrames::new()));
    let error_cb = move |err| eprintln!("Windows luidspreker streamfout: {}", err);
    let stream = match format {
        SampleFormat::F32 => {
            let shared = shared.clone();
            device.build_output_stream(
                &config,
                move |buffer: &mut [f32], _| fill(buffer, channels, rate, &shared, |s| s),
                error_cb, None
            )
        }
        SampleFormat::I16 => {
            let shared = shared.clone();
            device.build_output_stream(
                &config,
                move |buffer: &mut [i16], _| fill(buffer, channels, rate, &shared,
                                                   |s| (s * 32767.0) as i16),
                error_cb, None
            )
        }
        SampleFormat::U16 => {
            let shared = shared.clone();
            device.build_output_stream(
                &config,
                move |buffer: &mut [u16], _| fill(buffer, channels, rate, &shared,
                                                   |s| ((s * 32767.0) + 32768.0) as u16),
                error_cb, None
            )
        }
        _ => return Err(format!("Onbekend output formaat {:?}", format)),
    }.map_err(|e| format!("Luidspreker openen: {}", e))?;
    stream.play().map_err(|e| format!("Luidspreker activeren: {}", e))?;
    Ok(Speaker {
        _stream: stream, name,
        format: format!("{} Hz, {} kanalen, {:?}", config.sample_rate.0, channels, format),
        frames: shared,
    })
}

pub fn open() -> Result<Speaker, String> {
    let host = cpal::default_host();
    let mut candidates = Vec::new();
    if let Some(default) = host.default_output_device() { candidates.push(default); }
    if let Ok(devices) = host.output_devices() { candidates.extend(devices); }
    let mut seen = Vec::new();
    let mut problems = Vec::new();
    for device in candidates {
        let name = device.name().unwrap_or_else(|_| "Onbekend".to_string());
        if seen.contains(&name) { continue; }
        seen.push(name.clone());
        match start_one(&device) {
            Ok(speaker) => return Ok(speaker),
            Err(err) => problems.push(format!("{}: {}", name, err)),
        }
    }
    Err(if problems.is_empty() {
        "Windows heeft geen geluidsuitvoerapparaten gevonden.".to_string()
    } else { problems.join(" | ") })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn uses_48000_samples_at_native_rate() {
        let mut q = OutputFrames::new();
        q.add(&vec![32767; 480]);
        for _ in 0..480 {
            assert!(q.next(48000.0) > 0.9);
        }
    }
    #[test]
    fn converts_mono_to_44100_hz_stereo_buffer() {
        let mut q = OutputFrames::new();
        q.add(&vec![16384; 48000]);
        let queue = Arc::new(Mutex::new(q));
        let mut out = vec![0f32; 4410 * 2];
        fill(&mut out, 2, 44100.0, &queue, |s| s);
        assert_eq!(out[20], out[21]);
        assert!(out[20] > 0.4);
    }
}
