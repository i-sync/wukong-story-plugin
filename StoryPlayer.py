# -*- coding: utf-8-*-
import os
import re
import json
from robot import utils, config, logging, constants
from robot.Player import MusicPlayer
from robot.sdk.AbstractPlugin import AbstractPlugin

logger = logging.getLogger(__name__)

"""
给故事播放器插件使用的，
在 MusicPlayer 的基础上添加了播放状态保存与读取。
"""
class StoryPlayer(MusicPlayer):
    SLUG = 'StoryPlayer'

    def __init__(self, playlist, plugin, **kwargs):
        super(StoryPlayer, self).__init__(playlist, plugin, **kwargs)
        self.album = None
        self.playlist = None
        self.idx = None
        self.status_path = os.path.join(constants.DATA_PATH, 'story')

    def play(self):
        logger.debug('StoryPlayer play')
        path = self.playlist[self.idx]
        logger.info(f'目前正在播放：{self.playlist[self.idx]}')
        super(MusicPlayer, self).stop()
        super(MusicPlayer, self).play(path, False, self.next)

    def next(self):
        logger.debug('StoryPlayer next')
        super(MusicPlayer, self).stop()
        self.idx = (self.idx+1) % len(self.playlist)
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
        super(MusicPlayer, self).stop()
        self.album = album
        self.playlist = playlist
        self.idx = self.get_playstatus()
        # check if continue
        if self.idx:
            self.plugin.say(f'继续播放{album}: {self.get_song_name()}', wait=True)
        self.play()
    
    def get_playstatus(self):
        tmp_status_path = os.path.join(self.status_path, f'{self.album}.json')
        if not os.path.exists(tmp_status_path):
            return 0
        return json.loads(utils.get_file_content(tmp_status_path))['idx']

    def save_playstatus(self):
        tmp_status_path = os.path.join(self.status_path, f'{self.album}.json')
        if os.path.exists(tmp_status_path):
            os.remove(tmp_status_path)
        with open(tmp_status_path, 'w+', encoding='utf-8') as f:
            f.write(json.dumps({'idx': self.idx}))
    
    def get_song_name(self):
        path = self.playlist[self.idx]
        name = path.split('/')[-1]
        name = re.sub(r"^\d*\.*","", name)
        return re.sub(r"\.mp3|\.m4a|\.wav", "", name)

class Plugin(AbstractPlugin):

    IS_IMMERSIVE = True  # 这是个沉浸式技能

    def __init__(self, con):
        super(Plugin, self).__init__(con)
        self.player = None
        self.index_path = os.path.join(constants.DATA_PATH, 'story', 'index.json')
        self.song_index = json.loads(utils.get_file_content(self.index_path))
        self.song_list = None
        self.album_data = None       

    def get_song_list(self, text):
        logger.info(f"检索内容：{text}")
        for i in self.song_index:
            if text in i["name"] or text in i["origin_name"] or any(text in x or x in text for x in i["keys"]):
                logger.info(f"找到故事：{i['name']}, 路径：{i['path']}")
                self.album_data = i
                return [os.path.join(i["path"], song) for song in i["list"]]
        return []

    def handle(self, text, parsed):  
        if not self.player:
            self.player = StoryPlayer(None, self)
        
        if '播放' in text:
            input = re.sub(r'[^\w\u4e00-\u9fa5]+', '', text)
            input = re.sub(r".*播放", '', input)
            self.song_list = self.get_song_list(input)
            #logger.info(self.song_list)
            if len(self.song_list) == 0:
                self.clearImmersive()  # 去掉沉浸式
                self.say(f'没有找到{text}相关资源，播放失败')
                return                
            self.player.update_playlist(self.album_data['name'], self.song_list)
            #self.player.play()
        elif self.nlu.hasIntent(parsed, 'MUSICRANK'):
            self.player.play()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_NEXT'):
            self.player.next()
        elif self.nlu.hasIntent(parsed, 'CHANGE_TO_LAST'):
            self.player.prev()
        elif self.nlu.hasIntent(parsed, 'CHANGE_VOL'):
            slots = self.nlu.getSlots(parsed, 'CHANGE_VOL')
            for slot in slots:
                if slot['name'] == 'user_d':
                    word = self.nlu.getSlotWords(parsed, 'CHANGE_VOL', 'user_d')[0]
                    if word == '--HIGHER--':
                        self.player.turnUp()
                    else:
                        self.player.turnDown()
                    return
                elif slot['name'] == 'user_vd':
                    word = self.nlu.getSlotWords(parsed, 'CHANGE_VOL', 'user_vd')[0]
                    if word == '--LOUDER--':
                        self.player.turnUp()
                    else:
                        self.player.turnDown()

        elif self.nlu.hasIntent(parsed, 'PAUSE'):
            self.player.pause()
        elif self.nlu.hasIntent(parsed, 'CONTINUE'):
            self.player.resume()
        elif self.nlu.hasIntent(parsed, 'CLOSE_MUSIC'):
            self.player.stop()
            self.clearImmersive()  # 去掉沉浸式
        else:
            self.say('没听懂你的意思呢，要停止播放，请说停止播放', wait=True)
            self.player.resume()

    def pause(self):
        if self.player:
            self.player.stop()

    def restore(self):
        if self.player and not self.player.is_pausing():
            self.player.resume()

    def isValidImmersive(self, text, parsed):
        return any(self.nlu.hasIntent(parsed, intent) for intent in ['CHANGE_TO_LAST', 'CHANGE_TO_NEXT', 'CHANGE_VOL', 'CLOSE_MUSIC', 'PAUSE', 'CONTINUE'])

    def isValid(self, text, parsed):
        return "播放" in text

