import json
import logging
import os
import subprocess
from base64 import b64decode
from os.path import join
from pathlib import Path
from urllib.parse import urljoin

import requests


class Vimeo:
    def __init__(self, playlist_url: str, output_path: str):
        self.playlist_url = playlist_url
        self.output_path = output_path
        Path(self.output_path).mkdir(parents=True, exist_ok=True)

    def send_request(self) -> bool:
        self.response = requests.get(url=self.playlist_url)
        return self.response.status_code == 200

    def parse_playlist(self) -> bool:
        try:
            parsed = json.loads(self.response.text)
        except Exception:
            return False

        self.clip_id = parsed.get('clip_id')
        self.videos = sorted(parsed.get('video', []), key=lambda p: p.get('width', 1) * p.get('height', 1), reverse=True)
        self.audios = sorted(parsed.get('audio', []), key=lambda p: p.get('sample_rate', 1) * p.get('bitrate', 1), reverse=True)
        self.main_base = urljoin(self.playlist_url, parsed.get('base_url', ''))
        return bool(self.videos or self.audios)

    def _save_playlist(self, stream: dict, content_type: str) -> tuple[str, str]:
        stream_base = urljoin(self.main_base, stream.get('base_url', ''))
        segments_to_write = []
        max_duration = 0

        for segments in stream.get('segments', []):
            duration = segments.get('end') - segments.get('start')
            max_duration = max(max_duration, duration)
            segments_to_write.append({
                'url': urljoin(stream_base, segments.get('url')),
                'duration': duration
            })

        init = f"{stream.get('id', 'NO_ID')}_{content_type}_init.mp4"
        with open(join(self.output_path, init), 'wb') as f:
            f.write(b64decode(stream.get('init_segment')))

        playlist = f"{stream.get('id', 'NO_ID')}_{content_type}.m3u8"
        with open(join(self.output_path, playlist), 'w') as f:
            f.writelines([
                '#EXTM3U\n',
                '#EXT-X-VERSION:4\n',
                '#EXT-X-MEDIA-SEQUENCE:0\n',
                '#EXT-X-PLAYLIST-TYPE:VOD\n',
                f'#EXT-X-MAP:URI="{init}"\n',
                f'#EXT-X-TARGETDURATION:{int(round(max_duration)) + 1}\n'
            ])
            for segment in segments_to_write:
                f.write(f"#EXTINF:{segment['duration']}\n")
                f.write(f"{segment['url']}\n")
            f.write("#EXT-X-ENDLIST\n")

        return playlist, init

    def _save_video_stream(self, video: dict) -> dict:
        playlist_url, init = self._save_playlist(video, 'video')
        return {
            'url': playlist_url,
            'resolution': f"{video.get('width')}x{video.get('height')}",
            'bandwidth': video.get('bitrate'),
            'average_bandwidth': video.get('avg_bitrate'),
            'codecs': video.get('codecs'),
            'init': init
        }

    def _save_audio_stream(self, audio: dict) -> dict:
        playlist_url, init = self._save_playlist(audio, 'audio')
        return {
            'url': playlist_url,
            'channels': audio.get('channels'),
            'bitrate': audio.get('bitrate'),
            'sample_rate': audio.get('sample_rate'),
            'init': init
        }

    def _save_master(self, video_streams: list, audio_streams: list) -> str:
        master = f"master_{self.clip_id}.m3u8"
        with open(join(self.output_path, master), 'w') as f:
            f.writelines([
                '#EXTM3U\n',
                '#EXT-X-INDEPENDENT-SEGMENTS\n'
            ])
            for idx, audio in enumerate(audio_streams):
                f.write(
                    f'#EXT-X-MEDIA:TYPE=AUDIO,URI="{audio["url"]}",GROUP-ID="audio",NAME="{audio["bitrate"]/1000}_{audio["sample_rate"]}_{idx}",CHANNELS="{audio["channels"]}"\n'
                )
            for video in video_streams:
                f.write(
                    f'#EXT-X-STREAM-INF:BANDWIDTH={video["bandwidth"]},AVERAGE-BANDWIDTH={video["average_bandwidth"]},CODECS="{video["codecs"]}",RESOLUTION={video["resolution"]},AUDIO="audio"\n'
                )
                f.write(f'{video["url"]}\n')

        return master

    def save_media(self) -> tuple[str, list]:
        video_streams = list(map(self._save_video_stream, self.videos))
        audio_streams = list(map(self._save_audio_stream, self.audios))
        master = self._save_master(video_streams, audio_streams)
        return master, [*video_streams, *audio_streams]


def download_vimeo_json(url: str, output_path: str) -> str:
    vimeo = Vimeo(url, output_path)

    if not vimeo.send_request():
        raise Exception("Request to URL failed.")
    if not vimeo.parse_playlist():
        raise Exception("Failed to parse playlist.")

    master_file, streams = vimeo.save_media()

    exe_path = "N_m3u8DL-RE.exe"
    full_master_path = join(output_path, master_file)
    output_file = join(output_path, f"{vimeo.clip_id}.mkv")

    subprocess.run(
        [exe_path, full_master_path, "-M", "format=mkv", "--save-name", vimeo.clip_id, "--no-log"],
        check=True
    )

    # Cleanup
    for stream in streams:
        for key in ["url", "init"]:
            file_path = join(output_path, stream.get(key))
            if os.path.exists(file_path):
                os.remove(file_path)
    if os.path.exists(full_master_path):
        os.remove(full_master_path)

    return output_file
