# -*- coding: utf-8-*-
import os
import re
import json
import time
import mplayer
import platform
import subprocess
from robot import utils, config, logging, constants
from robot.Player import AbstractPlayer
from robot.sdk.AbstractPlugin import AbstractPlugin

logger = logging.getLogger(__name__)

class MPlayer(AbstractPlayer):

    SLUG = 'MPlayer'

    def __init__(self, **kwargs):
        super(MPlayer, self).__init__(**kwargs)
        self.EOFArgs = "-msglevel global=6"
        self.playing = False
        self.player = mplayer.Player(args=self.EOFArgs.split())
        self.player.stdout.connect(self.handle_player_output)
        logger.debug(f'Init MPlayer, {self.player}')
        self.onCompleteds = []

    def play(self, src, time_pos, onCompleted=None):
        if os.path.exists(src) or src.startswith('http'):
            if onCompleted is not None:
                self.onCompleteds.append(onCompleted)

            if not self.player.is_alive():
                self.player = mplayer.Player(args=self.EOFArgs.split())
                self.player.stdout.connect(self.handle_player_output)

            logger.debug(f'mplayer play time_pos: {time_pos}')
            self.player.loadfile(src)
            if time_pos:
                self.player.time_pos = time_pos
            self.playing = True
        else:
            logger.critical(f'file path not exists: {src}')

    def handle_player_output(self, line):
        #logger.debug(f'mplayer stdout: {line}')
        if line.startswith('EOF code: 1'): # 正常播放完成， 如果直接加载其它文件状态：EOF code: 2.
            self.playing = False

            # exec next play
            logger.debug(f"play completed, exec next play.")
            """
            for onCompleted in self.onCompleteds:
                if onCompleted is not None:
                    onCompleted()
            """
            # fix always loop.
            if self.onCompleteds and len(self.onCompleteds):
                self.onCompleteds.pop(0)()

    def appendOnCompleted(self, onCompleted):
        if onCompleted is not None:
            self.onCompleteds.append(onCompleted)

    def is_playing(self):
        return self.playing

    @property
    def time_pos(self):
        return self.player.time_pos

    @property
    def speed(self):
        return self.player.speed

"""
给故事播放器插件使用的，
在 MPlayer 的基础上添加了播放列表，状态保存与读取。
"""
class StoryPlayer(MPlayer):

    SLUG = 'StoryPlayer'

    def __init__(self, playlist, plugin, **kwargs):
        super(StoryPlayer, self).__init__(**kwargs)
        self.album = None
        self.playlist = playlist
        self.plugin = plugin
        self.pausing = False
        self.idx = 0
        self.status_path = os.path.join(constants.DATA_PATH, 'story')

    def play(self, time_pos=0):
        logger.debug('StoryPlayer play')
        path = self.playlist[self.idx]
        logger.info(f'目前正在播放：{self.playlist[self.idx]}')
        self.plugin.say(f'{self.get_song_name()}', wait=True)
        super().play(path, time_pos, self.next)

    def next(self):
        logger.debug('StoryPlayer next')
        self.idx += 1
        if self.idx >= len(self.playlist):
            self.idx -= 1
            self.plugin.say(f'当前已经是最后一集了' if self.playing else f'{self.album} 已经全部播放完毕, 请试试其它内容', wait = True)

            # remove play status when album play completed.
            if not self.playing:
                self.remove_playstatus()
        else:
            self.play()
    
    def prev(self):
        logger.debug('StoryPlayer prev')
        self.idx -= 1 # (self.idx-1) % len(self.playlist)
        if self.idx < 0:
            self.idx = 0
            logger.info(f'当前已经是第一集了')
            self.plugin.say(f'当前已经是第一集了', wait = True)
        else:
            self.play()

    def first(self):
        logger.debug('StoryPlayer play first')
        self.idx = 0
        self.play()

    def last(self):
        logger.debug('StoryPlayer play first')
        self.idx = len(self.playlist) - 1
        self.play()

    def change_to(self, num):
        logger.debug(f'StoryPlay change to {num}')
        if num < 1 or num > len(self.playlist):
            self.plugin.say(f'超出当前列表范围, 请重试', wait = True)
        else:
            self.idx = num - 1
            self.play()

    def resume(self):
        logger.debug('StoryPlayer resume')
        if self.player.paused:
            self.player.pause()
    
    def pause(self):
        logger.debug('StoryPlayer pause')
        if self.player.filename and not self.player.paused:
            logger.debug(f'MPlayer is running: {self.player.filename} , pause status: { self.player.paused}, paused...')
            self.player.pause()
            #save play status
            self.save_playstatus()
    
    def stop(self):
        logger.debug('StoryPlayer stop')
        if self.player.is_alive():
            self.player.stop()

    def quit(self):
        logger.debug('StoryPlayer quit')
        if self.player.is_alive():
            self.player.quit()
    
    def update_playlist(self, album, playlist):
        self.album = album
        self.playlist = playlist
        time_pos = 0
        self.status = self.get_playstatus()
        # check if continue
        if self.status and (self.status['idx'] or self.status['time_pos']):
            self.idx = self.status['idx']
            time_pos= self.status['time_pos']
            logger.debug(f'from file read playlist time_pos: {time_pos}')
            self.plugin.say(f'继续播放:{album}', wait=True)
        else:
            self.idx = 0
            self.plugin.say(f'马上为您播放:{album}', wait=True)

        self.play(time_pos)
    
    def get_playstatus(self):
        """
        Read Last Play Status
        """
        tmp_status_path = os.path.join(self.status_path, f'{self.album}.json')
        if not os.path.exists(tmp_status_path):
            return None

        # check file content if is none
        file_content = utils.get_file_content(tmp_status_path)
        if not file_content:
            return None
        return json.loads(file_content)

    def save_playstatus(self):
        """
        Save Current Play Status
        """
        # skip when album is none
        if not self.album or not self.time_pos:
            return

        tmp_status_path = os.path.join(self.status_path, f'{self.album}.json')
        if os.path.exists(tmp_status_path):
            os.remove(tmp_status_path)
        logger.debug(f'save play time pos: {self.time_pos}')
        with open(tmp_status_path, 'w+', encoding='utf-8') as f:
            f.write(json.dumps({'idx': self.idx, 'time_pos': self.time_pos}))
    
    def remove_playstatus(self):
        """
        remove play status when album play completed 
        """
        # skip when album is none
        if not self.album:
            return

        tmp_status_path = os.path.join(self.status_path, f'{self.album}.json')
        if os.path.exists(tmp_status_path):
            os.remove(tmp_status_path)

    def get_song_name(self):
        path = self.playlist[self.idx]
        name = path.split('/')[-1]
        name = re.sub(r"^\d*\.*","", name)
        return re.sub(r"\.mp3|\.m4a|\.wav", "", name)

    def turn_up(self):
        system = platform.system()
        if system == 'Darwin':
            res = subprocess.run(['osascript', '-e', 'output volume of (get volume settings)'], shell=False, capture_output=True, universal_newlines=True)
            volume = int(res.stdout.strip())
            volume += 10
            if volume >= 100:
                volume = 100
                self.plugin.say('音量已经最大啦', wait=True)
            subprocess.run(['osascript', '-e', 'set volume output volume {}'.format(volume)])
        elif system == 'Linux':
            res = subprocess.run(["amixer sget Master | grep 'Mono:' | awk -F'[][]' '{ print $2 }'"], shell=True, capture_output=True, universal_newlines=True)
            print(res.stdout)
            if res.stdout != '' and res.stdout.strip().endswith('%'):
                volume = int(res.stdout.strip().replace('%', ''))
                volume += 10
                if volume >= 100:
                    volume = 100
                    self.plugin.say('音量已经最大啦', wait=True)
                subprocess.run(['amixer', 'set', 'Master', '{}%'.format(volume)])
            else:
                subprocess.run(['amixer', 'set', 'Master', '10%+'])
        else:
            self.plugin.say('当前系统不支持调节音量', wait=True)
        self.resume()

    def turn_down(self):
        system = platform.system()
        if system == 'Darwin':
            res = subprocess.run(['osascript', '-e', 'output volume of (get volume settings)'], shell=False, capture_output=True, universal_newlines=True)
            volume = int(res.stdout.strip())
            volume -= 10
            if volume <= 10:
                volume = 10
                self.plugin.say('音量已经很小啦', wait=True)
            subprocess.run(['osascript', '-e', 'set volume output volume {}'.format(volume)])
        elif system == 'Linux':
            res = subprocess.run(["amixer sget Master | grep 'Mono:' | awk -F'[][]' '{ print $2 }'"], shell=True, capture_output=True, universal_newlines=True)
            if res.stdout != '' and res.stdout.endswith('%'):
                volume = int(res.stdout.replace('%', '').strip())
                volume -= 10
                if volume <= 10:
                    volume = 10
                    self.plugin.say('音量已经最小啦', wait=True)
                subprocess.run(['amixer', 'set', 'Master', '{}%'.format(volume)])
            else:
                subprocess.run(['amixer', 'set', 'Master', '10%-'])
        else:
            self.plugin.say('当前系统不支持调节音量', wait=True)
        self.resume()

    def turn_to(self, volume):
        logger.debug(f"Volume change to :{volume}")
        system = platform.system()
        if system == 'Darwin':
            subprocess.run(['osascript', '-e', 'set volume output volume {}'.format(volume*10)])
        elif system == 'Linux':
            subprocess.run(['amixer', 'set', 'Master', f'{volume*10}%'])
        else:
            self.plugin.say('当前系统不支持调节音量', wait=True)
        self.resume()

class Plugin(AbstractPlugin):

    IS_IMMERSIVE = True  # 这是个沉浸式技能

    def __init__(self, con):
        super(Plugin, self).__init__(con)
        self.player = StoryPlayer(None, self)
        self.index_path = os.path.join(constants.DATA_PATH, 'story', 'index.json')
        self.song_index = None
        self.song_list = None
        self.album_data = None

    def get_song_list(self, text):
        logger.info(f"检索内容：{text}")
        #严格匹配
        for i in self.song_index:
            if text == i["name"]:
                logger.info(f"找到故事：{i['name']}, 路径：{i['path']}")
                self.album_data = i
                return [os.path.join(i["path"], song) for song in i["list"]]
        #模糊匹配
        for i in self.song_index:
            if text in i["name"] or text in i["origin_name"] or any(text in x for x in i["keys"]):
                logger.info(f"找到故事：{i['name']}, 路径：{i['path']}")
                self.album_data = i
                return [os.path.join(i["path"], song) for song in i["list"]]
        return []

    def handle(self, text, parsed):  
        #if not self.player:
        #   self.player = StoryPlayer(None, self)
        
        # check index file.
        if not self.song_index:
            if not os.path.exists(self.index_path):
                logger.info('索引文件不存在,请先更新索引')
                self.say('索引文件不存在,请先更新索引', cache=True, wait=True)
                self.clearImmersive()  # 去掉沉浸式
                return
            else:
                self.song_index = json.loads(utils.get_file_content(self.index_path))

        if '播放' in text and not self.nlu.hasIntent(parsed, 'CHANGE_TO'):
            input_text = re.sub(r'[^\w\u4e00-\u9fa5]+', '', text)
            input_text = re.sub(r".*播放", '', input_text)
            self.song_list = self.get_song_list(input_text)
            #logger.info(self.song_list)
            if len(self.song_list) == 0:
                """
                pausing=True: 说明已经播放过相关故事，但处于暂停状态
                puasing=Fasle:
                    playing=True: 说明正在播放
                    playing=False: 说明从来没有开始播放， 去掉沉浸式。
                """
                if not self.player.pausing and not self.player.is_playing():
                    self.say(f'没有找到{input_text}相关资源，播放失败', wait=True)
                    self.clearImmersive()  # 去掉沉浸式
                    return
                else:
                    self.say(f'没有找到{input_text}相关资源', wait=True)
                    return
            self.player.update_playlist(self.album_data['name'], self.song_list)
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_NEXT'):
            self.player.next()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_PREV'):
            self.player.prev()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_FIRST'):
            self.player.first()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_LAST'):
            self.player.last()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO'):
            word = self.nlu.getSlotWords(parsed, 'CHANGE_TO', 'user_story_index')[0]
            self.player.change_to(int(float(word)))
        elif self.nlu.hasIntent(parsed, 'CHANGE_VOL_UP'):
            self.player.turn_up()
        elif self.nlu.hasIntent(parsed, 'CHANGE_VOL_DOWN'):
            self.player.turn_down()
        elif self.nlu.hasIntent(parsed, 'CHANGE_VOL_TO'):
            word = self.nlu.getSlotWords(parsed, 'CHANGE_VOL_TO', 'user_vol_num')[0]
            self.player.turn_to(int(word))
        elif self.nlu.hasIntent(parsed, 'PAUSE'):
            self.player.pause()
            self.player.pausing = True
        elif self.nlu.hasIntent(parsed, 'CONTINUE'):
            self.player.resume()
            self.player.pausing = False
        elif self.nlu.hasIntent(parsed, 'CLOSE_MUSIC'):
            self.player.stop()
            self.clearImmersive()  # 去掉沉浸式
        else:
            self.say('没听懂你的意思呢，要停止播放，请说停止播放', cache=True, wait=True)
            self.player.pausing = False
            self.player.resume()

    def pause(self):
        if self.player:
            self.player.pause()

    def restore(self):
        if self.player and not self.player.pausing:
            self.player.resume()

    def isValidImmersive(self, text, parsed):
        return any(self.nlu.hasIntent(parsed, intent) for intent in ['CHANGE_TO_PREV', 'CHANGE_TO_NEXT', 'CHANGE_TO_FIRST', 'CHANGE_TO_LAST', 'CHANGE_TO', 'CHANGE_VOL_UP', 'CHANGE_VOL_DOWN', 'CHANGE_VOL_TO', 'CLOSE_MUSIC', 'PAUSE', 'CONTINUE'])

    def isValid(self, text, parsed):
        return "播放" in text

