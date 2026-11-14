FROM nousresearch/hermes-agent:latest

COPY apply_mission_context_patch.py /tmp/apply_mission_context_patch.py
RUN python3 /tmp/apply_mission_context_patch.py && rm -f /tmp/apply_mission_context_patch.py
