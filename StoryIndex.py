# -*- coding: utf-8-*-
# 创建、重建系列故事索引
import os
import re
import json
import time
from robot import utils, config, logging, constants
from robot.sdk.AbstractPlugin import AbstractPlugin

logger = logging.getLogger(__name__)

class Plugin(AbstractPlugin):

    SLUG = 'StoryIndex'
    
    def __init__(self, con):
        super(Plugin, self).__init__(con)
        self.music_path = config.get(f"/{self.SLUG}/musicpath")
        index_path = os.path.join(constants.DATA_PATH, 'story')
        if not os.path.exists(index_path):
            os.mkdir(index_path)
        self.index_file = os.path.join(index_path, 'index.json')
        self.content_file = os.path.join(index_path, 'content.json')

    def build_index(self):
        # remove before rebuild
        utils.check_and_delete(self.index_file)
        utils.check_and_delete(self.content_file)

        res = []
        content = []
        for root, dirs, files in os.walk(self.music_path):
            #print(root)
            if len(dirs):
                continue
            album_name = root.split('/')[-1]
            keys = [key for key in re.split(r'[^\w\u4e00-\u9fa5]+', album_name) if key]
            res.append({'name': ''.join(keys), 'origin_name': album_name, 'keys':keys, 'path': root, 'count':len(files), 'list': sorted(files)})
            content.append({'name': ''.join(keys), 'origin_name': album_name, 'keys':keys, 'path': root, 'count':len(files)})
            logger.info(content[-1])
        
        if len(res):
            with open(self.index_file, 'w+', encoding='utf-8') as f:
                f.write(json.dumps(res, ensure_ascii=False))
            with open(self.content_file, 'w+', encoding='utf-8') as f:
                f.write(json.dumps(content, ensure_ascii=False))

    def handle(self, text, parsed):
        if not os.path.exists(self.music_path):
            logger.warn(f'故事路径不存在:{self.music_path}')
            self.say('故事路径配置错误,请检查配置', cache=True)
            return

        try:
            self.say('正在更新索引', cache=True, wait=True)
            self.build_index()
            self.say('更新完成', cache=True)
        except Exception as e:
            logger.error(e)
            self.say('抱歉，更新索引失败', cache=True)

    def isValid(self, text, parsed):
        return any(word in text for word in ["索引", "创建索引", "重建索引", "更新索引"])
