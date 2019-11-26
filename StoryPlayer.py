# -*- coding: utf-8-*-
import os
import re
import json
import time
import mplayer
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
        self.onCompleteds = []

    def play(self, src, time_pos, onCompleted=None):
        if os.path.exists(src) or src.startswith('http'):
            if onCompleted is not None:
                self.onCompleteds.append(onCompleted)

            if not self.player.is_alive():
                self.player = mplayer.Player(args=self.EOFArgs.split())
                self.player.stdout.connect(self.handle_player_output)

            self.player.loadfile(src)
            self.player.time_pos = time_pos
            self.playing = True

            # waiting for play completed.
            while True:
                if not self.playing:
                    break
                time.sleep(0.5)

            for onCompleted in self.onCompleteds:
                if onCompleted is not None:
                    onCompleted()
        else:
            logging.critical(f'file path not exists: {src}')

    def handle_player_output(self, line):
        if line.startswith('EOF code:'):
            self.playing = False

    def appendOnCompleted(self, onCompleted):
        if onCompleted is not None:
            self.onCompleteds.append(onCompleted)

    def stop(self):
        #if self.player.is_alive():
        #    self.player.quit()
        self.pause()

    def quit(self):
        if self.player.is_alive():
            self.player.quit()

    def pause(self):
        if not self.player.paused:
            self.player.pause()

    def resume(self):
        if self.player.paused:
            self.player.pause()

    def is_playing(self):
        return self.playing

    def is_pausing(self):
        return self.player.paused

    @property
    def time_pos(self):
        return self.player.time_pos

    @property
    def speed(self):
        return self.player.speed

    @property
    def volume(self):
        return self.player.volume

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
        self.idx = 0
        self.status_path = os.path.join(constants.DATA_PATH, 'story')

    def play(self, time_pos=0):
        logger.debug('StoryPlayer play')
        path = self.playlist[self.idx]
        logger.info(f'目前正在播放：{self.playlist[self.idx]}')
        self.plugin.say(f'{self.get_song_name()}', cache=True, wait=True)
        super().stop()
        super().play(path, time_pos, self.next)
        # save play status
        self.save_playstatus()

    def next(self):
        logger.debug('StoryPlayer next')
        super().stop()
        self.idx = (self.idx+1) % len(self.playlist)
        self.play()
    
    def prev(self):
        logger.debug('StoryPlayer prev')
        super().stop()
        self.idx = (self.idx-1) % len(self.playlist)
        self.play()

    def first(self):
        logger.debug('StoryPlayer play first')
        super().stop()
        self.idx = 0
        self.play()

    def resume(self):
        super().resume()
        self.onCompleteds = [self.next]
    
    def pause(self):
        logger.debug('StoryPlayer pause')
        super().pause()
        self.save_playstatus()
    
    def stop(self):
        logger.debug('StoryPlayer stop')
        super().stop()
        self.save_playstatus()
    
    def update_playlist(self, album, playlist):
        super().stop()
        self.album = album
        self.playlist = playlist
        time_pos = 0
        self.status = self.get_playstatus()
        # check if continue
        if self.status and (self.status['idx'] or self.status['time_pos']):
            time_pos= self.status['time_pos']
            self.plugin.say(f'继续播放:{album}', cache=True, wait=True)
        else:
            self.plugin.say(f'马上为您播放:{album}', cache=True, wait=True)

        self.play(time_pos)
    
    def get_playstatus(self):
        tmp_status_path = os.path.join(self.status_path, f'{self.album}.json')
        if not os.path.exists(tmp_status_path):
            return None
        return json.loads(utils.get_file_content(tmp_status_path))

    def save_playstatus(self):
        tmp_status_path = os.path.join(self.status_path, f'{self.album}.json')
        if os.path.exists(tmp_status_path):
            os.remove(tmp_status_path)
        with open(tmp_status_path, 'w+', encoding='utf-8') as f:
            f.write(json.dumps({'idx': self.idx, 'time_pos': self.time_pos if self.time_pos else 0}))
    
    def get_song_name(self):
        path = self.playlist[self.idx]
        name = path.split('/')[-1]
        name = re.sub(r"^\d*\.*","", name)
        return re.sub(r"\.mp3|\.m4a|\.wav", "", name)

    def turn_up(self):
        volume = self.volume
        volume += 10
        if volume >= 100:
            volume = 100
            self.plugin.say('音量已经最大啦', wait=True)
        self.volume = volume
        self.resume()

    def turn_down(self):
        volume = self.volume
        volume -= 10
        if volume <= 10:
            volume = 10
            self.plugin.say('音量已经最小啦', wait=True)
        self.volume = volume
        self.resume()

class Plugin(AbstractPlugin):

    IS_IMMERSIVE = True  # 这是个沉浸式技能

    def __init__(self, con):
        super(Plugin, self).__init__(con)
        self.player = None
        self.index_path = os.path.join(constants.DATA_PATH, 'story', 'index.json')
        self.song_index = None
        self.song_list = None
        self.album_data = None

    def get_song_list(self, text):
        logger.info(f"检索内容：{text}")
        for i in self.song_index:
            if text in i["name"] or text in i["origin_name"] or any(text in x for x in i["keys"]):
                logger.info(f"找到故事：{i['name']}, 路径：{i['path']}")
                self.album_data = i
                return [os.path.join(i["path"], song) for song in i["list"]]
        return []

    def handle(self, text, parsed):  
        if not self.player:
            self.player = StoryPlayer(None, self)
        
        # check index file.
        if not self.song_index:
            if not os.path.exists(self.index_path):
                logging.info('索引文件不存在,请先更新索引')
                self.say('索引文件不存在,请先更新索引', cache=True)
            else:
                self.song_index = json.loads(utils.get_file_content(self.index_path))

        if '播放' in text:
            input = re.sub(r'[^\w\u4e00-\u9fa5]+', '', text)
            input = re.sub(r".*播放", '', input)
            self.song_list = self.get_song_list(input)
            #logger.info(self.song_list)
            if len(self.song_list) == 0:
                self.clearImmersive()  # 去掉沉浸式
                self.say(f'没有找到{text}相关资源，播放失败', cache=True)
                return
            self.player.update_playlist(self.album_data['name'], self.song_list)
            #self.player.play()
        elif self.nlu.hasIntent(parsed, 'MUSICRANK'):
            self.player.play()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_NEXT'):
            self.player.next()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_LAST'):
            self.player.prev()
        elif self.nlu.hasIntent(parsed, 'RESTART_MUSIC'):
            self.player.first()
        elif self.nlu.hasIntent(parsed, 'CHANGE_VOL'):
            slots = self.nlu.getSlots(parsed, 'CHANGE_VOL')
            for slot in slots:
                if slot['name'] == 'user_d':
                    word = self.nlu.getSlotWords(parsed, 'CHANGE_VOL', 'user_d')[0]
                    if word == '--HIGHER--':
                        self.player.turn_up()
                    else:
                        self.player.turn_down()
                    return
                elif slot['name'] == 'user_vd':
                    word = self.nlu.getSlotWords(parsed, 'CHANGE_VOL', 'user_vd')[0]
                    if word == '--LOUDER--':
                        self.player.turn_up()
                    else:
                        self.player.turn_down()

        elif self.nlu.hasIntent(parsed, 'PAUSE'):
            self.player.pause()
        elif self.nlu.hasIntent(parsed, 'CONTINUE'):
            self.player.resume()
        elif self.nlu.hasIntent(parsed, 'CLOSE_MUSIC'):
            self.player.stop()
            self.clearImmersive()  # 去掉沉浸式
        else:
            self.say('没听懂你的意思呢，要停止播放，请说停止播放', cache=True, wait=True)
            self.player.resume()

    def pause(self):
        if self.player:
            self.player.stop()

    def restore(self):
        if self.player and not self.player.is_pausing():
            self.player.resume()

    def isValidImmersive(self, text, parsed):
        return any(self.nlu.hasIntent(parsed, intent) for intent in ['CHANGE_TO_LAST', 'CHANGE_TO_NEXT', 'RESTART_MUSIC', 'CHANGE_VOL', 'CLOSE_MUSIC', 'PAUSE', 'CONTINUE'])

    def isValid(self, text, parsed):
        return "播放" in text

