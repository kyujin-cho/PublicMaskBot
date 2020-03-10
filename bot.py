import logging
import os
import re
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

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
address_regex = re.compile(r'^([^\(]+)\((.+)\)$')

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
        if not (33.0 <= value.location.latitude <= 43.0) or not (124.0 <= value.location.longitude <= 132.0):
            return self._failure('공적 마스크 API에서 지원하지 않는 위치에요.')
        return value.location

@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    await message.reply('반갑습니다! 공적 마스크 위치를 알려주는 텔레그램 봇입니다. 현재 위치를 보내면 근처 500미터 이내의 마스크 판매처와 재고를 알려드립니다.')

@dp.message_handler(commands=['lookup'])
async def start_lookup(message: types.Message):
    response = ''
    m_split = message.text.strip().split(' ')
    print(m_split)
    if len(m_split) == 1:
        range_ = 500
    else:
        try:
            range_ = t.ToInt(gte=1, lte=5000).check(m_split[1].strip())
        except t.DataError as e:
            print(e)
            range_ = 500
            response = '반경이 너무 크거나 작아요. 기본값인 500미터로 고정할게요.\n'
        response += '이 메세지의 답변 메세지로 현재 위치를 보내주세요.'
    sent_message = await bot.send_message(message.chat.id, response, reply_to_message_id=message.message_id)
    store_range_info[sent_message.message_id] = range_

@dp.message_handler(content_types=ContentTypes.LOCATION)
async def get_location(message: types.Message):
    rr_mid = None
    print(store_range_info)
    print(message.reply_to_message)
    if message.reply_to_message is not None and message.reply_to_message.message_id in store_range_info.keys():
        rr_mid = message.reply_to_message.message_id
        m = store_range_info[rr_mid]
    else:
        m = 500
    try:
        location: types.Location = LocationChecker().check(value=message)
    except t.DataError as e:
        return await message.reply(e.error)
    
    body = {
        'lat': str(location.latitude),
        'lng': str(location.longitude),
        'm': str(m)
    }
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f'{MASK_API}/storesByGeo/json', params=body) as resp:
            resp_body: Mapping[str, Any] = await resp.json()
            reply = f' 반경 {m}미터에서 마스크 판매처를 {resp_body["count"]}군데 찾았어요.\n'
            for store in resp_body['stores']:
                if match := address_regex.match(store['addr']):
                    address, abstract = match.groups()
                else:
                    address = store['addr']
                    abstract = ''
                
                encoded_address = urlencode({'a': address + store['name']})
                print(encoded_address)
                reply_tmp = f'{store_type_desc[store["type"]]} [{store["name"]} ({abstract})](https://map.kakao.com/?q={encoded_address[2:]}): '
                if store['remain_stat'] is None:
                    reply_tmp += '❌ 정보 미제공\n'
                    continue
                reply_tmp += f'*{mask_stat_desc[store["remain_stat"]]}* '
                reply_tmp += f'_({store["stock_at"]} 기준)_'
                reply_tmp += '\n'
                if len(reply_tmp) + len(reply) > 4096:
                    reply += '판매처가 너무 많아요. 반경을 좁혀서 다시 시도해 주세요.\n'
                    break
                reply += reply_tmp
        await message.reply(reply, parse_mode='Markdown', disable_web_page_preview=True)
    if rr_mid is not None:
        del store_range_info[rr_mid]

if __name__ == '__main__':
    if BOT_TOKEN is None:
        print('Bot Token env not provided!')
        exit(-1)
    executor.start_polling(dp, skip_updates=True)
