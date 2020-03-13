'''
Copyright (C) 2020 ~  Kyujin Cho

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

'''

import asyncio
import logging
import os
from pathlib import Path
import pickle
import re
import signal
import shutil
from typing import MutableMapping, Mapping, Any
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ContentTypes
import aiohttp
from dotenv import load_dotenv
import trafaret as t

load_dotenv(verbose=True)

BOT_TOKEN = os.getenv('BOT_TOKEN')
MASK_API = 'https://8oi9s0nnth.apigw.ntruss.com/corona19-masks/v1'

address_regex = re.compile(r'^([^\(]+)\((.+)\)$')
dumped_range_info_path = Path('./range.binary')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

mask_stat_desc = {
    'empty': '⚫️ 1개 이하',
    'few': '🔴 2개 ~ 29개',
    'some': '🟡 30개 ~99개',
    'plenty': '🟢 100개 이상'
}
store_type_desc = {
    '01': '💊',
    '02': '📮',
    '03': '🌾'
}
store_range_info = {}


class LocationChecker(t.Trafaret):
    def check_and_return(self, value: types.Message) -> types.Location:
        if not type(value) == types.Message:
            return self._failure('Value is not a Message')
        if value.location is None:
            return self._failure('Message does not contain location info')
        if not (33.0 <= value.location.latitude <= 43.0) or \
           not (124.0 <= value.location.longitude <= 132.0):
            return self._failure('공적 마스크 API에서 지원하지 않는 위치에요.')
        return value.location


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    await message.reply('반갑습니다! 공적 마스크 위치를 알려주는 텔레그램 봇입니다. '
                        '현재 위치를 보내면 근처 500미터 이내의 마스크 판매처와 재고를 알려드립니다.')


@dp.message_handler(commands=['lookup'])
async def start_lookup(message: types.Message):
    logging.info(f'Received message {message.text}')
    response = ''
    m_split = message.text.strip().split(' ')
    if len(m_split) == 1:
        range_ = 500
    else:
        try:
            range_ = t.ToInt(gte=1, lte=5000).check(m_split[1].strip())
        except t.DataError as e:
            logging.error(e)
            range_ = 500
            response = '반경이 너무 크거나 작아요. 기본값인 500미터로 고정할게요.\n'
    response += '이 메세지의 답변 메세지로 현재 위치를 보내주세요.'
    sent_message = await bot.send_message(message.chat.id, response,
                                          reply_to_message_id=message.message_id,
                                          reply_markup=types.ForceReply())
    store_range_info[(sent_message.message_id, message.chat.id,)] = range_


@dp.message_handler(content_types=ContentTypes.LOCATION)
async def get_location(message: types.Message):
    rr_mid = None
    m = 500
    if message.reply_to_message is not None:
        rep_msg = message.reply_to_message
        _rr_mid = (rep_msg.message_id, rep_msg.chat.id,)
        if _rr_mid in store_range_info.keys():
            m = store_range_info[_rr_mid]
            rr_mid = _rr_mid
    try:
        location: types.Location = LocationChecker().check(value=message)
    except t.DataError as e:
        return await message.reply(e.error)

    body = {
        'lat': str(location.latitude),
        'lng': str(location.longitude),
        'm': str(m)
    }
    tmp_msg = await bot.send_message(message.chat.id, '검색중이에요. 잠시 기다려주세요.',
                                     reply_to_message_id=message.message_id)

    async def coro():
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f'{MASK_API}/storesByGeo/json', params=body) as resp:
                resp_body: Mapping[str, Any] = await resp.json()
                reply = f'반경 *{m}*미터에서 마스크 판매처를 *{resp_body["count"]}*군데 찾았어요.\n'
                if resp_body['count'] == 0:
                    reply = '저런! 근처에 마스크 판매처가 존재하지 않아요.'
                for store in resp_body['stores']:
                    if match := address_regex.match(store['addr']):  # noqa
                        address, abstract = match.groups()
                    else:
                        address = store['addr']
                        abstract = ''
                    address = (f'{address.split(",")[0]} {store["name"]}'
                                .replace(',', ' ').replace(' ', '+'))
                    reply_tmp = (f'{store_type_desc[store["type"]]} [{store["name"]} ({abstract})]'
                                 f'(https://map.kakao.com/?q={address}): ')
                    if 'remain_stat' not in store.keys() or store['remain_stat'] is None:
                        reply_tmp += '❌ 정보 미제공\n'
                        continue
                    reply_tmp += f'*{mask_stat_desc[store["remain_stat"]]}* '
                    reply_tmp += f'_({store["stock_at"]} 기준)_'
                    reply_tmp += '\n'
                    if len(reply_tmp) + len(reply) > (4096 - 33):
                        reply += '판매처가 너무 많아서, 나머지 판매처의 출력은 생략했어요.\n'
                        break
                    reply += reply_tmp
                await bot.edit_message_text(chat_id=message.chat.id, message_id=tmp_msg.message_id,
                                            text=reply, parse_mode='Markdown',
                                            disable_web_page_preview=True)
    ex = await asyncio.gather(coro(), return_exceptions=True)
    if len(ex) > 0 and isinstance(ex[0], Exception):
        logging.error(ex[0])
        await bot.edit_message_text(chat_id=message.chat.id, message_id=tmp_msg.message_id,
                                    text='저런! 마스크 판매처 정보를 불러오는 데 실패했어요. 다시 시도해 주세요.')
    if rr_mid is not None:
        del store_range_info[rr_mid]


def dump_range_info(signum, frame):
    with open(dumped_range_info_path, 'wb') as fw:
        fw.write(pickle.dumps(store_range_info))
    logging.info('Dumped info:')
    logging.info(store_range_info)
    exit(0)


if __name__ == '__main__':
    if BOT_TOKEN is None:
        logging.error('Bot Token env not provided!')
        exit(-1)
    if dumped_range_info_path.exists():
        try:
            with open(dumped_range_info_path, 'rb') as fr:
                store_range_info = pickle.loads(fr.read())
            logging.info('Loaded info:')
            logging.info(store_range_info)
        except:
            logging.warning('Failed recoving range info')
        os.remove(dumped_range_info_path)
    signal.signal(signal.SIGINT, dump_range_info)

    executor.start_polling(dp, skip_updates=True)
