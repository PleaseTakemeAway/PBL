# Qwen3.6-27B in BF16 (55.6 GB of weights), the reasoning model of the colleague's
# 27/30 run. Pipelined over three 24 GB RTX A5000s: the last stage holds the LM
# head and needs 0.95 to leave room for a 16k-token request. The colleague ran it
# on one 90 GB GPU.
model=Qwen/Qwen3.6-27B
gpu=1,2,3
parallel=pipeline
vllm_args=(--max-model-len=16384 --max-num-seqs=16 --gpu-memory-utilization=0.95)
