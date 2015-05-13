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
        self.users = PikabuUserInfo(**self.settings)
        self.posts = PikabuPosts(**self.settings)

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

    def rate(self, action, post_id):
        if not post_id:
            raise ValueError('Invalid post ID')
        if action == '+' or action == 1:
            act = '+'
        elif action == '-' or action == 0:
            act = '-'
        else:
            return False

        rate_data = {
            'i': post_id,
            'type': act
        }
        
        page = self.request('ajax/dig.php', method='POST', data=rate_data)
        return page

class PikabuComments(PikaService):

    def get(self, post_id):
        if post_id:
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
        else:
            raise ValueError('Invalid post ID')

    def add(self, text, post_id, parent_id=0):
        if post_id and text:
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
        else:
            raise ValueError('Invalid post ID or text comment')

    def rate(self, action, post_id, comment_id):
        if comment_id and post_id:
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
        else:
            raise ValueError('Invalid post or comment ID')

class PikabuUserInfo(PikaService):
    def __init__(self, **settings):
        self.html = None
        self.info = None
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
    """Профиль авторизованного пользователя"""
    def __init__(self, **settings):
        self.html = None
        self.settings = settings

    def get(self):
        """Возвращает информацию о пользователе"""
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
        """Возвращает количество подписчиков"""
        user_list = self.html.find('ul', 'b-user-menu-list').findAll('li')[1].text
        return int(''.join(s for s in user_list if s.isdigit()))

class PikabuTopTags(PikaService):

    def get(self, limit=10):
        if limit > 0:
            page = self.request('html.php?id=faq')
            tags = BeautifulSoup(page)
            tag_list = list(zip(
                [x.text for x in tags.findAll('span', 'tag no_ch')],
                [int(y.text) for y in tags.findAll('span', 'tag_count')]
            ))
            return tag_list[:limit]
        else:
            return False


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
