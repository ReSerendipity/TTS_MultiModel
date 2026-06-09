import requests
import json

r = requests.post(
    'http://127.0.0.1:7869/api/generate/streaming_sse',
    data={
        'text': '测试文本',
        'persona_name': 'gf1',
        'instruction': '',
        'lang': 'Auto',
        'cfg_value': '2.0',
        'inference_timesteps': '10',
        'denoise': 'true'
    },
    stream=True,
    timeout=120
)

print(f'Status: {r.status_code}')
lines_count = 0
audio_count = 0
event_types = {}

for line in r.iter_lines():
    if line:
        lines_count += 1
        line_str = line.decode('utf-8')
        if line_str.startswith('event:'):
            etype = line_str[6:].strip()
            event_types[etype] = event_types.get(etype, 0) + 1
            if etype == 'audio':
                audio_count += 1
            elif etype == 'done':
                print(f'>>> DONE event: {line_str}')
            elif etype == 'error':
                print(f'>>> ERROR event: {line_str}')

print(f'\nTotal lines: {lines_count}')
print(f'Audio events: {audio_count}')
print(f'Event types: {json.dumps(event_types)}')
