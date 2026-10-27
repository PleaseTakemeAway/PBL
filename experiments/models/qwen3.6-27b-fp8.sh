# Qwen3.6-27B with Qwen's FP8 weights (about half of BF16), for two 24 GB RTX
# A5000s with tensor parallelism. The A5000 has no FP8 units, so vLLM keeps the
# weights in FP8 and computes in 16 bit. Not yet run here; if the KV cache does
# not fit, add --reason-vllm-arg=--enforce-eager or lower --max-num-seqs.
model=Qwen/Qwen3.6-27B-FP8
gpu=0,1
parallel=tensor
vllm_args=(--max-model-len=16384 --max-num-seqs=4 --gpu-memory-utilization=0.92)
