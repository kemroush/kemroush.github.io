import { pipeline, env } from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3/+esm';

env.allowLocalModels = false;

const MODEL_ID = 'onnx-community/whisper-medium-ONNX';

// Device-specific precision. On WebGPU (Metal on the user's Mac) fp16 is stable
// and half the size of fp32; the q8/int8 *encoder* is what produced garbage, so
// we avoid it. On the WASM/CPU fallback we use fp32 encoder + q8 decoder, which
// is proven correct on CPU.
const DTYPE = {
  // fp32 encoder: some WebGPU stacks (incl. this user's Mac) produce broken
  // output with the fp16 encoder, so we keep the encoder at fp32 and only
  // quantize the decoder for speed.
  webgpu: { encoder_model: 'fp32', decoder_model_merged: 'q4' },
  wasm: { encoder_model: 'fp32', decoder_model_merged: 'q8' },
};

const cache = {};

async function getTranscriber(device, progress_callback) {
  if (cache[device]) return cache[device];
  cache[device] = await pipeline('automatic-speech-recognition', MODEL_ID, {
    device,
    dtype: DTYPE[device],
    progress_callback,
  });
  return cache[device];
}

// WebGPU can silently emit numerically broken output on some hardware/drivers.
// This shows up two ways: an endlessly repeating string, OR a near-empty result
// (e.g. "Pou a") for audio that clearly contains speech. Detect both so we can
// retry on the WASM backend instead of handing the user garbage.
function looksBroken(text, durationSec) {
  const t = (text || '').trim();
  // Near-empty output for non-trivial audio.
  const chars = t.replace(/\s+/g, '').length;
  if (durationSec >= 4 && chars < Math.max(8, durationSec * 2)) return true;
  // Long repeating loop.
  const words = t.split(/\s+/);
  if (words.length >= 12) {
    const tail = words.slice(-40);
    if (new Set(tail).size / tail.length <= 0.2) return true;
  }
  return false;
}

function transcribe(asr, audio, language) {
  return asr(audio, {
    language: language || null,
    task: 'transcribe',
    chunk_length_s: 30,
    stride_length_s: 5,
    return_timestamps: true,
  });
}

self.onmessage = async (event) => {
  const { type, audio, language } = event.data;
  if (type !== 'transcribe') return;

  const progress_callback = (data) => self.postMessage({ type: 'progress', data });

  try {
    let device = 'webgpu';
    let asr;
    try {
      self.postMessage({ type: 'status', message: 'Načítám model (WebGPU)…' });
      asr = await getTranscriber('webgpu', progress_callback);
    } catch (err) {
      device = 'wasm';
      self.postMessage({ type: 'status', message: 'WebGPU není dostupné, používám WASM (pomalejší)…' });
      asr = await getTranscriber('wasm', progress_callback);
    }

    const backup = device === 'webgpu' ? Float32Array.from(audio) : null;
    const durationSec = audio.length / 16000;

    self.postMessage({ type: 'status', message: 'Přepisuji zvuk…' });
    let result = await transcribe(asr, audio, language);

    if (device === 'webgpu' && looksBroken(result.text, durationSec)) {
      self.postMessage({ type: 'status', message: 'WebGPU vrátil chybný výstup, opakuji přes WASM (pomalejší)…' });
      const wasmAsr = await getTranscriber('wasm', progress_callback);
      result = await transcribe(wasmAsr, backup, language);
    }

    self.postMessage({ type: 'result', text: result.text });
  } catch (err) {
    self.postMessage({ type: 'error', message: err?.message || String(err) });
  }
};
