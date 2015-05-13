#!/usr/bin/python3
# -*- coding: utf-8 -*-
import re
import json
import calendar
import requests
import datetime
from bs4 import BeautifulSoup

IS_LOGGED = False
XCSRF_TOKEN = None
SITE_URL = 'http://pikabu.ru/'
PIKABU_SESS = requests.Session()


class PikaService(object):

    def __init__(self, **settings):
        if 'login' not in settings or 'password' not in settings:
            raise ValueError('Не указан логин и пароль')
        self.settings = settings

    def request(self, url, data=None, method='GET', referer=SITE_URL, custom_headers=None, need_auth=True):
        global IS_LOGGED
        XCSRF_TOKEN = requests.get(SITE_URL).cookies['PHPSESS']
        post_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36',
            'Referer': referer,
            'Host': 'pikabu.ru',
            'Origin': 'http://pikabu.ru',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Csrf-Token': XCSRF_TOKEN,
            'X-Requested-With': 'XMLHttpRequest'
        }

        if need_auth and not IS_LOGGED:
            login_data = {
                'mode': 'login',
                'username': self.settings['login'],
                'password': self.settings['password'],
                'remember': 0
            }

            r = PIKABU_SESS.post(SITE_URL + 'ajax/ajax_login.php', data=login_data, headers=post_headers, cookies={'PHPSESS': XCSRF_TOKEN})
            r = json.loads(r.text)
            if int(r['logined']) == 0:
                raise ValueError('Неверно указан логин или пароль')
            if int(r['logined']) == -1:
                raise ValueError(['error'])
            IS_LOGGED = True

        req = requests.Request(method, SITE_URL + url,
            data = data,
            headers = custom_headers if(custom_headers is not None) else post_headers,
            cookies = {'PHPSESS': XCSRF_TOKEN}
        )
        prepped = req.prepare()
        resp = PIKABU_SESS.send(prepped)
        resp.raise_for_status()

        return resp.text


class PikabuPosts(PikaService):

    def rate(self, action, post_id):
        if post_id:
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
        else:
            raise ValueError('Invalid post ID')
        


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
                comment_list.append(ObjectComments(int(comment['id']), int(comment['rating']),
                                                   comment['nick'], int(comment['answer']),
                                                   comment_date, comment.text))
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
            referer = requests.head('%s/story/_%i' % (SITE_URL, post_id), allow_redirects=False).headers['location']
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

            referer = requests.head('%s/story/_%i' % (SITE_URL, post_id), allow_redirects=False).headers['location']
            custom_headers = {
                'Accept': '*/*',
                'Host': 'pikabu.ru',
                'Referer': referer,
                'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36'
            }

            rate_data = {
                'type': 'comm',
                'i': comment_id,
                'story': post_id,
                'dir': act
            }
            
            page = self.request('dig.php', data=rate_data, custom_headers=custom_headers, referer=referer)
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
        self.info = self.html.find('div', {'style':'padding-top: 0px; line-height: 15px;'}).text.split('\n')

        return ObjectUserInfo(login, self.get_dor(),
            self.get_rating(), self.get_avatar(), self.get_comments(),
            self.get_news(), self.get_actions(), self.get_awards())

    def get_dor(self):
        """Возвращает дату регистрации пользователя"""
        return self.parse_date(self.info[3])

    def get_rating(self):
        """Возвращает рейтинг юзера"""
        return int(self.info[4].split()[1])

    def get_avatar(self):
        """Возвращает аватар юзера"""
        return self.html.find('img')['src']

    def get_comments(self):
        """Возвращает количество комментариев юзера"""
        return int(self.info[5].split()[1])

    def get_news(self):
        """Возвращает массив с количеством новостей"""
        return list(map(lambda x: int(x), re.findall(r'\d+', self.info[6])))

    def get_actions(self):
        """Возвращает массив с количество + и - юзера"""
        return [int(self.info[10].split()[0]), int(self.info[12].split()[0])]

    def get_awards(self):
        """Возвращает список наград пользователя"""
        _ = self.html.find('div', 'awards_wrap').findAll('img')
        return list(map(lambda x: (x['title'], x['src']), _))

    def parse_date(date):
    if 'сегодня' in date:
        return calendar.timegm(datetime.datetime.today().utctimetuple())
    part_str = date.split()
    year, month, day = 1, 1, 1
    for val, index in [(int(x), i) for i, x in enumerate(part_str) if x.isdigit()]:
        if part_str[index+1].startswith('ле') or part_str[index+1].startswith('го'):
            year += val
        elif part_str[index+1].startswith('ме'):
            month += val
        elif part_str[index+1].startswith('не'):
            day += 7*val
        elif part_str[index+1].startswith('дн') or part_str[index+1].startswith('де'):
            day += val
    diff = datetime.datetime.today()-datetime.datetime(year, month, day)
    reg_date = datetime.datetime(1, 1, 1)+datetime.timedelta(diff.days)
    return calendar.timegm(reg_date.utctimetuple())

class PikabuProfile(PikabuUserInfo):
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
        return ObjectUserInfo(self.settings['login'], profile.dor,
            profile.rating, profile.comments, profile.avatar,
            profile.news, profile.actions, profile.awards, self.get_followers())

    def get_followers(self):
        """Возвращает количество подписчиков"""
        return int(''.join(s for s in self.html.find('ul', 'b-user-menu-list').findAll('li')[1].text if s.isdigit()))

class PikabuTopTags(PikaService):

    def get(self, limit=10):
        if limit > 0:
            page = self.request('html.php?id=faq')
            tags = BeautifulSoup(page)
            tag_list = list(zip(map(lambda x: x.text, tags.findAll('span', 'tag no_ch')), map(lambda y: int(y.text), tags.findAll('span', 'tag_count'))))
            return tag_list[:limit]
        else:
            return False


class ObjectUserInfo():

    def __init__(self, login, dor, rating, avatar, comments, news, actions, awards, followers=None):
        self.login = login
        self.dor = dor
        self.rating = rating
        self.avatar = avatar
        self.comments = comments
        self.news = news
        self.actions = actions
        self.awards = awards
        if followers is not None:
            self.followers = followers

class ObjectComments():

    def __init__(self, id, rating, nick, answer, date, text):
        self.id = id
        self.rating = rating
        self.author = nick
        self.answer = answer
        self.date = date
        self.text = text


class API:

    def __init__(self, **settings):
        self.settings = settings
        self.comments = PikabuComments(**self.settings)
        self.top_tags = PikabuTopTags(**self.settings)
        self.profile = PikabuProfile(**self.settings)
        self.users = PikabuUserInfo(**self.settings)
        self.posts = PikabuPosts(**self.settings)
