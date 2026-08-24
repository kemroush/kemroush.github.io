import { pipeline, env } from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3/+esm';

env.allowLocalModels = false;

const MODEL_ID = 'onnx-community/whisper-small';
const DTYPE = { encoder_model: 'fp32', decoder_model_merged: 'q4' };

const cache = {};

async function getTranscriber(device, progress_callback) {
  if (cache[device]) return cache[device];
  cache[device] = await pipeline('automatic-speech-recognition', MODEL_ID, {
    device,
    dtype: DTYPE,
    progress_callback,
  });
  return cache[device];
}

// WebGPU can silently emit numerically broken output on some hardware/drivers,
// which Whisper turns into an endlessly repeating string. Detect that so we can
// retry on the WASM backend instead of handing the user garbage.
function looksDegenerate(text) {
  if (!text) return true;
  const words = text.trim().split(/\s+/);
  if (words.length < 12) return false;
  const tail = words.slice(-40);
  const uniqueRatio = new Set(tail).size / tail.length;
  return uniqueRatio <= 0.2;
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

    self.postMessage({ type: 'status', message: 'Přepisuji zvuk…' });
    let result = await transcribe(asr, audio, language);

    if (device === 'webgpu' && looksDegenerate(result.text)) {
      self.postMessage({ type: 'status', message: 'WebGPU vrátil chybný výstup, opakuji přes WASM (pomalejší)…' });
      const wasmAsr = await getTranscriber('wasm', progress_callback);
      result = await transcribe(wasmAsr, backup, language);
    }

    self.postMessage({ type: 'result', text: result.text });
  } catch (err) {
    self.postMessage({ type: 'error', message: err?.message || String(err) });
  }
};
