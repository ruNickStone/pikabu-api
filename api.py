#!/usr/bin/python3
# -*- coding: utf-8 -*-

import re
import json
import calendar
import requests
import datetime
from bs4 import BeautifulSoup


def parse_date(date):
    if u'сегодня' in date:
        return calendar.timegm(datetime.datetime.today().utctimetuple())
    part_str = date.split()
    year, month, day = 1, 1, 1
    for val, index in [(int(x), i) for i, x in enumerate(part_str) if x.isdigit()]:
        if part_str[index+1].startswith(u'ле') or part_str[index+1].startswith(u'го'):
            year += val
        elif part_str[index+1].startswith(u'ме'):
            month += val
        elif part_str[index+1].startswith(u'не'):
            day += 7*val
        elif part_str[index+1].startswith(u'дн') or part_str[index+1].startswith(u'де'):
            day += val
    diff = datetime.datetime.today()-datetime.datetime(year, month, day)
    reg_date = datetime.datetime(1, 1, 1)+datetime.timedelta(diff.days)
    return calendar.timegm(reg_date.utctimetuple())


class API(object):

    site_url = 'http://pikabu.ru/'

    def __init__(self, **settings):
        self.settings = settings
        self.comments = PikabuComments(**self.settings)
        self.top_tags = PikabuTopTags(**self.settings)
        self.profile = PikabuProfile(**self.settings)
        self.posts = PikabuPosts(**self.settings)
        self.users = PikabuUserInfo(**self.settings)


class PikaService(object):

    pikabu_sess = requests.Session()

    def __init__(self, **settings):
        if 'login' not in settings or 'password' not in settings:
            raise ValueError('Не указан логин и пароль')
        self.is_logged = False
        self.settings = settings
        self.xcsrf_token = None

    def request(self, url, data=None, method='GET', referer=API.site_url,
                custom_headers=None, need_auth=True):
        self.xcsrf_token = requests.get(API.site_url).cookies['PHPSESS']
        post_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36',
            'Referer': referer,
            'Host': 'pikabu.ru',
            'Origin': 'http://pikabu.ru',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Csrf-Token': self.xcsrf_token,
            'X-Requested-With': 'XMLHttpRequest'
        }

        if need_auth and not self.is_logged:
            login_data = {
                'mode': 'login',
                'username': self.settings['login'],
                'password': self.settings['password'],
                'remember': 0
            }

            response = self.pikabu_sess.post(
                API.site_url + 'ajax/ajax_login.php',
                data=login_data,
                headers=post_headers,
                cookies={'PHPSESS': self.xcsrf_token}
            )

            response = json.loads(response.text)
            if int(response['logined']) == 0:
                raise ValueError('Неверно указан логин или пароль')
            if int(response['logined']) == -1:
                raise ValueError(['error'])
            self.is_logged = True

        req = requests.Request(
            method,
            API.site_url + url,
            data=data,
            headers=custom_headers if(custom_headers is not None) else post_headers,
            cookies={'PHPSESS': self.xcsrf_token}
        )

        prepped = req.prepare()
        resp = self.pikabu_sess.send(prepped)
        resp.raise_for_status()

        return resp.text


class PikabuPosts(PikaService):
    def __init__(self, **settings):
        self.post = None
        self.post_head = None
        self.settings = settings
        PikaService.__init__(self, **settings)

    def get(self, cat='new', limit=20):
        if not isinstance(limit, int) or limit < 1:
            raise ValueError('Invalid limit')
        if cat not in ['hot', 'best', 'new']:
            raise ValueError('Wrong category')

        page_count = limit // 20 + 1 if(limit % 20 != 0) else int(limit / 20)
        for i in range(page_count):
            page = self.request('%s?page=%i' % (cat, i))
            html = BeautifulSoup(page)
            posts = html.findAll('table', 'b-story inner_wrap')
            posts_list = []
            for post in posts:
                self.post = post
                self.post_head =  self.post.find('div', 'b-story__content')
                posts_list.append(
                    ObjectPosts(
                        self.post_id, self.url, self.title, 
                        self.description, self.content, self.author, 
                        self.add_date, self.comments, self.rating, self.tag_list
                        )
                    )
        return posts_list

    @property
    def post_id(self):
        return self.post.find('tr', 'newload')['abbr']

    @property
    def url(self):
        return self.post.find('a', 'story_link')['href']

    @property
    def title(self):
        return self.post.find('a', 'story_link').text.strip()

    @property
    def description(self):
        if self.post_head['id'][:3] == 'pic' or self.post_head['id'][:5] == 'video':
            return self.post.find('div', 'short').text

    @property
    def content(self):
        if self.post_head['id'][:7] == 'textDiv':
            return self.post_head.text.strip()
        elif self.post_head['id'][:3] == 'pic':
            return self.post_head.find('img')['src']
        else:
            return self.post_head.find('div', 'b-video')['data-url']

    @property
    def author(self):
        return self.post.find('a', style='padding-right: 0').text
    
    @property
    def add_date(self):
        return self.post.find('a', 'detailDate')['title']

    @property
    def comments(self):
        return int(''.join(s for s in self.post.find('a', 'b-link').text if s.isdigit()))

    @property
    def rating(self):
        rating = self.post.find('li', 'curs').text
        return None if(rating.strip() == '') else int(rating)
    
    @property
    def tag_list(self):
        tag_list = self.post.find('span', 'story_tag_list').findAll('a')
        return list(map(lambda x: x.text, tag_list))

    @property
    def post_type(self):
        if self.post_head['id'][:4] == 'textDiv':
            return 'text'
        elif post_head['id'][:3] == 'pic':
            return 'pic'
        else:
            return 'video'


    def rate(self, action, post_id):
        if not isinstance(post_id, int) and post_id < 0:
            raise ValueError('Invalid post ID')

        if action == '+' or action == 1:
            act = '+'
        elif action == '-' or action == 0:
            act = '-'
        else:
            raise ValueError('Invalid action')

        rate_data = {
            'i': post_id,
            'type': act
        }

        page = self.request('ajax/dig.php', method='POST', data=rate_data)
        return page


class PikabuComments(PikaService):

    def __init__(self, **settings):
        PikaService.__init__(self, **settings)
        self.settings = settings

    def get(self, post_id):
        if not isinstance(post_id, int) or post_id < 0:
            raise ValueError('Invalid post ID')

        page = self.request('generate_xml_comm.php?id=%i' % post_id, need_auth=False)
        comment_list = []
        xml = BeautifulSoup(page)
        comments = xml.comments.findAll('comment')
        for comment in comments:
            comment_date = calendar.timegm(datetime.datetime.strptime(
                comment['date'], '%Y-%m-%d %H:%M').utctimetuple())  # date to timestamp
            comment_list.append(
                ObjectComments(
                    int(comment['id']),
                    int(comment['rating']),
                    comment['nick'],
                    int(comment['answer']),
                    comment_date, comment.text
                )
            )

        return comment_list

    def add(self, text, post_id, parent_id=0):
        if not isinstance(post_id, int) or post_id < 0 or not text:
            raise ValueError('Invalid post ID')

        comment_data = {
            'act': 'addcom',
            'id': post_id,
            'comment': text,
            'parentid': parent_id,
            'include': 0,
            'comment_images': ''
        }

        path = '%s/story/_%i' % (API.site_url, post_id)
        referer = requests.head(path, allow_redirects=False).headers['location']
        page = self.request('ajax.php', comment_data, method='POST', referer=referer)
        response = json.loads(page)

        return True if(response['type'] == 'done') else response['text']

    def rate(self, action, post_id, comment_id):
        if not isinstance(comment_id, int) or comment_id < 0:
            raise ValueError('Invalid comment ID')
        if not isinstance(post_id, int) or post_id < 0:
            raise ValueError('Invalid post ID')

        if action == '+' or action == 1:
            act = 1
        elif action == '-' or action == 0:
            act = 0
        else:
            raise ValueError('Invalid action')

        path = '%s/story/_%i' % (API.site_url, post_id)
        referer = requests.head(path, allow_redirects=False).headers['location']
        custom_headers = {
            'Accept': '*/*',
            'Host': 'pikabu.ru',
            'Referer': referer,
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36'
        }

        rate_data = {
            'type': 'comm',
            'i': comment_id,
            'story': post_id,
            'dir': act
        }

        page = self.request(
            'dig.php',
            data=rate_data,
            custom_headers=custom_headers,
            referer=referer
        )

        return page


class PikabuUserInfo(PikaService):

    def __init__(self, **settings):
        self.html = None
        self.info = None
        PikaService.__init__(self, **settings)
        self.settings = settings

    def get(self, login):
        page = self.request('profile/%s' % login, need_auth=False)
        self.html = BeautifulSoup(page).find('div', 'profile_wrap')
        info = self.html.find('div', {'style':'padding-top: 0px; line-height: 15px;'})
        self.info = info.text.split('\n')
        return ObjectUserInfo(
            login,
            self.dor,
            self.rating,
            self.avatar,
            self.comments,
            self.news,
            self.actions,
            self.awards
        )

    @property
    def dor(self):
        """Возвращает дату регистрации пользователя"""
        return parse_date(self.info[3])

    @property
    def rating(self):
        """Возвращает рейтинг юзера"""
        return int(self.info[4].split()[1])

    @property
    def avatar(self):
        """Возвращает аватар юзера"""
        return self.html.find('img')['src']

    @property
    def comments(self):
        """Возвращает количество комментариев юзера"""
        return int(self.info[5].split()[1])

    @property
    def news(self):
        """Возвращает массив с количеством новостей"""
        return list(map(int, re.findall(r'\d+', self.info[6])))

    @property
    def actions(self):
        """Возвращает массив с количество + и - юзера"""
        return [int(self.info[10].split()[0]), int(self.info[12].split()[0])]

    @property
    def awards(self):
        """Возвращает список наград пользователя"""
        _ = self.html.find('div', 'awards_wrap').findAll('img')
        return list([(x['title'], x['src']) for x in _])


class PikabuProfile(PikaService):

    def __init__(self, **settings):
        self.html = None
        PikaService.__init__(self, **settings)
        self.settings = settings

    def get(self):
        page = self.request('freshitems.php', need_auth=True)
        self.html = BeautifulSoup(page)
        profile = PikabuUserInfo()
        profile = profile.get(self.settings['login'])
        return ObjectUserInfo(
            self.settings['login'],
            profile.dor,
            profile.rating,
            profile.comments,
            profile.avatar,
            profile.news,
            profile.actions,
            profile.awards,
            self.followers
        )

    @property
    def followers(self):
        count = self.html.find('ul', 'b-user-menu-list').findAll('li')[1].text
        return int(''.join(s for s in count if s.isdigit()))


class PikabuTopTags(PikaService):

    def __init__(self, **settings):
        PikaService.__init__(self, **settings)
        self.settings = settings

    def get(self, limit=10):
        if not isinstance(limit, int) or limit < 0:
            raise ValueError('Invalid limit')

        page = self.request('html.php?id=faq')
        tags = BeautifulSoup(page)
        tag_list = list(zip(
            [x.text for x in tags.findAll('span', 'tag no_ch')],
            [int(y.text) for y in tags.findAll('span', 'tag_count')]
        ))
        return tag_list[:limit]


class ObjectPosts():

    def __init__(self, post_id, url, title, description,
        content, author, time, comments, rating, tags):
        self.id = post_id
        self.url = url
        self.title = title
        self.description = description
        self.content = content
        self.author = author
        self.time = time
        self.comments = comments
        self.rating = rating
        self.tags = tags


class ObjectUserInfo(object):

    def __init__(self, login, dor, rating, avatar, comments,
                 news, actions, awards, followers=None):
        self.login = login
        self.dor = dor
        self.rating = rating
        self.avatar = avatar
        self.comments = comments
        self.news = news
        self.actions = actions
        self.awards = awards
        if followers is None:
            followers = []
        self.followers = followers


class ObjectComments(object):

    def __init__(self, id, rating, nick, answer, date, text):
        self.id = id
        self.rating = rating
        self.author = nick
        self.answer = answer
        self.date = date
        self.text = text
