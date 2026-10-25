# DeepSeek-OCR-2 (6.8 GB of weights), the OCR model of the colleague's 27/30 run.
# Sized for one 24 GB RTX A5000; the colleague used 0.20 of a 90 GB GPU. On a
# smaller GPU raise the share, e.g. --ocr-vllm-arg=--gpu-memory-utilization=0.80
# for a 12 GB card.
model=deepseek-ai/DeepSeek-OCR-2
vllm_args=(--max-model-len=8192 --max-num-seqs=16 --gpu-memory-utilization=0.50)
