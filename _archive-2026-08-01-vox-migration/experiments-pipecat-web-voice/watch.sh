#!/usr/bin/env bash
# vox live watcher — filters the bot log for the events that matter during
# a voice chat, writes them to ~/.intraface/state/vox-watch.log.
#
# Filters:
#   - Tool calls: register_check, _tool_filler, function_calls_started
#   - LLM/STT/TTS errors
#   - Connection state changes
#   - Client disconnect / barge-in
#   - Any ERROR/CRITICAL line (catches anything the specific filters miss)
#
# Lines that don't match any filter are dropped to keep the output readable.
# Run with: ./watch.sh (backgrounds itself via nohup + disown)

set -u
LOG=~/.intraface/state/pipecat-web-voice.log
OUT=~/.intraface/state/vox-watch.log

# Marker line so each watcher session is findable in the output
{
  echo "==========================================================="
  echo "vox-watch started $(date -u '+%Y-%m-%dT%H:%M:%SZ') — pid $$"
  echo "filtering $LOG"
  echo "==========================================================="
} >> "$OUT"

# rg with multiline=false. Anchored alternation keeps noise out.
# --line-buffered so the tail -F | rg pipeline stays live.
#
# Patterns are matched against pipecat's actual log strings (verified
# 2026-07-29 by reading the raw log during a real chat):
#   - `_run_function_call` and `Calling function [name:id]` are what pipecat
#     emits when a tool actually fires
#   - `FunctionCallsStartedFrame` / `FunctionCallInProgressFrame` /
#     `FunctionCallResultFrame` are the lifecycle frames the aggregator emits
#   - `Generating TTS [...]` shows what the bot is about to speak
#   - `Transcription:` shows what the user said
exec tail -F -n0 "$LOG" 2>>"$OUT" | rg --line-buffered \
  -e 'Calling function \[' \
  -e '_run_function_call' \
  -e 'FunctionCalls?StartedFrame' \
  -e 'FunctionCallInProgressFrame' \
  -e 'FunctionCallResultFrame' \
  -e 'Generating TTS \[' \
  -e 'Transcription:' \
  -e 'ERROR|CRITICAL|Traceback' \
  -e '[Cc]lient (connected|disconnected)' \
  -e 'connection state changed to' \
  -e 'broadcast_interruption' \
  -e 'level=error|level=critical' \
  >> "$OUT"
