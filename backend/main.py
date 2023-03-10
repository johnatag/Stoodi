import asyncio
import shlex
import subprocess
from aiohttp import web
import socketio
import aiohttp_cors
import os
import subprocess
import shlex
from fnmatch import fnmatch
import whisper
from pathlib import Path
import json


from autocards import Autocards
from TextSummarizer import summarize_text

app = web.Application()

# Setup handlers
async def index(request):
    return web.Response(text="Hello world")

# Setup application routes.
app.router.add_route("GET", "/api", index)

cors = aiohttp_cors.setup(app, defaults={
"*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})

# Configure CORS on all routes.
for route in list(app.router.routes()):
    cors.add(route)

def find_files(directory, patterns):
    for root, dirs, files in os.walk(directory):
        for basename in files:
            for pattern in patterns:
                if fnmatch(basename, pattern):
                    filename = os.path.join(root, basename)
                    yield filename
                    
def convert_media_into_wav():
    media_patterns = ["*"]
    for filename in find_files('./files', media_patterns):
        mode = 0o777
        try:
            os.makedirs('./output', mode) 
        except OSError as error:
            print(error)
        output_name = filename.replace('./files', './output')
        subprocess.run(shlex.split(f'ffmpeg -i "{filename}" -ar 16000 -ac 1 -c:a pcm_s16le "{output_name}.wav"'))
        os.remove(filename)

def whisper_transcribe():
    audio_patterns = ["*.wav"]
    # Goes through all the folders in the Videos directory to retrieve the audio files for transcription
    for filename in find_files('./output', audio_patterns):
        subprocess.run(shlex.split(f'./whisper/main -m ./whisper/models/ggml-base.en.bin -f "{filename}" -t 8  -otxt'))
        os.remove(filename)

def read_transcription():
    pattern = ["*.txt"]
    for filename in find_files('./output', pattern):
        with open(filename) as f:
            return f.readlines()

def gen_flashcards(text: str):
    a = Autocards(in_lang="en", out_lang="en")
    a.clear_qa()
    a.consume_var(text, per_paragraph=True)
    a.to_json("./output/flashcards.json", prefix="")

sio = socketio.AsyncServer(
    async_mode='aiohttp',
    cors_allowed_origins='*', 
    async_handlers=True,
    ping_timeout=600
    )

@sio.event
async def connect(sid, environ, auth):
    print('connect ', sid)

@sio.event
async def disconnect(sid):
    print('disconnect ', sid)

@sio.event
async def upload_success(sid, data):
    print('upload success')
    convert_media_into_wav()
    await sio.emit('transcription_start', {
        'data': 'Transcription has started'
    })
    whisper_transcribe()
    txt = (" ".join(read_transcription()))
    
    await sio.emit('transcription_end', {
        'data': txt
    })
    
@sio.event
async def generate_summary(sid, data):
    summ = summarize_text(data)
    await sio.emit('generate_summary', {
        'data': summ
    })
    
@sio.event
async def generate_flashcards(sid, data):
    gen_flashcards(data)
    f = open('./output/flashcards_basic.json')
    data = json.load(f)
    
    await sio.emit('generate_flashcards', {
        'data': {
            "Questions": data['question'],
            "Answers": data['answer']
        }
    })
    
sio.attach(app)
    
if __name__ == '__main__':
    web.run_app(app, port=8089)
    