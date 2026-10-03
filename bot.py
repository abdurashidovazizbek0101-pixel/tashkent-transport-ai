import os
import math
import time
import asyncio
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

bot = Bot(TOKEN)
dp = Dispatcher()

OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
BBOX = "41.20,69.10,41.40,69.45"
HEADERS = {"User-Agent": "TashkentTransportBot/1.0"}

user_loc = {}
user_mode = {}
cache = {}

KB = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="🚌 Avtobuslar"), types.KeyboardButton(text="🚇 Metro")],
        [types.KeyboardButton(text="📍 Yaqin bekatlar", request_location=True)],
        [types.KeyboardButton(text="🗺️ Qayerga boraman?")],
    ],
    resize_keyboard=True,
)

LOC_KB = types.ReplyKeyboardMarkup(
    keyboard=[[types.KeyboardButton(text="📍 Joylashuvimni yuborish", request_location=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

NOTE = "\n\n⏱ Kelish vaqti hozircha ko'rsatilmaydi: jonli ma'lumot manbasi ulanmagan."


def distance(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742000 * math.asin(math.sqrt(a))


OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
last_error = {"text": ""}


async def overpass(query):
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        for url in OVERPASS_URLS:
            try:
                async with s.post(url, data={"data": query},
                                  timeout=aiohttp.ClientTimeout(total=90)) as r:
                    if r.status != 200:
                        last_error["text"] = f"{url.split('/')[2]}: HTTP {r.status}"
                        print(last_error["text"], flush=True)
                        continue
                    data = await r.json(content_type=None)
                    remark = str(data.get("remark", ""))
                    if "error" in remark.lower():
                        last_error["text"] = f"{url.split('/')[2]}: {remark[:80]}"
                        print(last_error["text"], flush=True)
                        continue
                    return data.get("elements", [])
            except Exception as e:
                last_error["text"] = f"{url.split('/')[2]}: {type(e).__name__}"
                print(last_error["text"], flush=True)
    return None


async def geocode(text):
    params = {"q": text + ", Toshkent", "format": "json", "limit": 1,
              "viewbox": "69.10,41.40,69.45,41.20", "bounded": 1}
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            async with s.get(NOMINATIM, params=params,
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", text)
    except Exception:
        pass
    return None


def route_label(tags):
    ref = tags.get("ref") or tags.get("name") or "?"
    if tags.get("from") and tags.get("to"):
        return f"{ref}: {tags['from']} → {tags['to']}"
    return ref


async def route_list(kind):
    key = "list_" + kind
    if key in cache and time.time() - cache[key][0] < 21600:
        return cache[key][1]
    els = await overpass(f"[out:json][timeout:60];rel[route={kind}]({BBOX});out tags;")
    if els is None:
        return None
    seen = {}
    for e in els:
        t = e.get("tags", {})
        key2 = t.get("ref") or t.get("name") or str(e["id"])
        seen.setdefault(key2, route_label(t))
    result = [seen[k] for k in sorted(seen, key=lambda x: (len(x), x))]
    cache[key] = (time.time(), result)
    return result


async def stops_and_routes(lat, lon, radius):
    q = (
        "[out:json][timeout:40];"
        f"(node(around:{radius},{lat},{lon})[highway=bus_stop];"
        f"node(around:{radius},{lat},{lon})[public_transport=platform][bus=yes];)->.s;"
        ".s out;"
        "rel(bn.s)[route=bus];out body;"
    )
    els = await overpass(q)
    if els is None:
        return None
    stops, rels, smap = {}, {}, {}
    for e in els:
        if e["type"] == "node":
            stops[e["id"]] = (e["lat"], e["lon"], e.get("tags", {}).get("name") or "Nomsiz bekat")
        elif e["type"] == "relation":
            rels[e["id"]] = e.get("tags", {})
    for e in els:
        if e["type"] == "relation":
            for mem in e.get("members", []):
                if mem["type"] == "node" and mem["ref"] in stops:
                    smap.setdefault(mem["ref"], set()).add(e["id"])
    return stops, rels, smap


async def send_chunks(message, title, lines):
    text = title + "\n\n"
    for line in lines:
        if len(text) + len(line) > 3500:
            await message.answer(text)
            text = ""
        text += line + "\n"
    if text.strip():
        await message.answer(text)


async def show_nearby(message, lat, lon):
    await message.answer("🔎 Yaqin bekatlar qidirilmoqda...")
    res = await stops_and_routes(lat, lon, 600)
    if res is None:
        return await message.answer("Xizmat hozir band. Birozdan keyin qayta urinib ko'ring.")
    stops, rels, smap = res
    if not stops:
        return await message.answer("600 m atrofida bekat topilmadi.")
    ordered = sorted(stops.items(), key=lambda kv: distance(lat, lon, kv[1][0], kv[1][1]))[:5]
    lines = []
    for sid, (slat, slon, name) in ordered:
        d = int(distance(lat, lon, slat, slon))
        refs = sorted({rels[r].get("ref") or rels[r].get("name") or "?" for r in smap.get(sid, [])},
                      key=lambda x: (len(x), x))
        lines.append(f"📍 {name} — {d} m")
        lines.append("🚌 " + (", ".join(refs[:12]) if refs else "yo'nalish ma'lumoti yo'q"))
        lines.append("")
    await send_chunks(message, "📍 Eng yaqin bekatlar:", lines)
    first = ordered[0][1]
    await message.answer_location(first[0], first[1])
    await message.answer("Eng yaqin bekat xaritada yuqorida." + NOTE, reply_markup=KB)


async def find_direct(message, origin, dest_text):
    await message.answer("🔎 Manzil qidirilmoqda...")
    g = await geocode(dest_text)
    if not g:
        return await message.answer("Bu manzilni topa olmadim. Boshqacha yozib ko'ring (masalan: Chorsu bozori).")
    dlat, dlon, dname = g
    a = await stops_and_routes(origin[0], origin[1], 600)
    b = await stops_and_routes(dlat, dlon, 600)
    if a is None or b is None:
        return await message.answer("Xizmat hozir band. Birozdan keyin qayta urinib ko'ring.")
    rels = {}
    rels.update(a[1])
    rels.update(b[1])
    ra = {r for s in a[2].values() for r in s}
    rb = {r for s in b[2].values() for r in s}
    common = ra & rb
    short = dname.split(",")[0]
    if not common:
        return await message.answer(
            f"🗺️ {short} tomonga to'g'ridan-to'g'ri aftobus topilmadi. "
            "Ko'chib o'tish kerak bo'lishi mumkin." + NOTE, reply_markup=KB)
    labels = sorted({route_label(rels[r]) for r in common}, key=lambda x: (len(x), x))[:10]
    await send_chunks(message, f"🗺️ {short} tomonga boradigan aftobuslar:", labels)
    await message.answer(
        "ℹ️ Yo'nalish tomoni (borish yoki qaytish) tekshirilmagan." + NOTE, reply_markup=KB)


@dp.message(CommandStart())
async def start(message: types.Message):
    user_mode.pop(message.from_user.id, None)
    await message.answer(
        "🚌 Assalomu alaykum!\n\n"
        "🚇 Toshkent Transport AI botiga xush kelibsiz.\n\n"
        "Quyidagilardan birini tanlang:",
        reply_markup=KB,
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📚 Yordam\n\n"
        "/start — Botni ishga tushirish\n"
        "/buses — Avtobuslar\n"
        "/metro — Metro\n"
        "/nearby — Yaqin bekatlar\n"
        "/route — Yo'nalish topish",
        reply_markup=KB,
    )


@dp.message(Command("buses"))
@dp.message(F.text == "🚌 Avtobuslar")
async def buses(message: types.Message):
    await message.answer("⏳ Yuklanmoqda, biroz kuting...")
    r = await route_list("bus")
    if r is None:
        return await message.answer("Ma'lumot manbasi javob bermadi. Keyinroq urinib ko'ring.\n(" + last_error["text"] + ")")
    if not r:
        return await message.answer("Ro'yxat bo'sh chiqdi.")
    await send_chunks(message, f"🚌 Toshkent avtobuslari ({len(r)} ta):", r)


@dp.message(Command("metro"))
@dp.message(F.text == "🚇 Metro")
async def metro(message: types.Message):
    r = await route_list("subway")
    if r is None:
        return await message.answer("Ma'lumot manbasi javob bermadi. Keyinroq urinib ko'ring.\n(" + last_error["text"] + ")")
    if not r:
        return await message.answer("Ro'yxat bo'sh chiqdi.")
    await send_chunks(message, "🚇 Toshkent metrosi:", r)


@dp.message(Command("nearby"))
async def nearby(message: types.Message):
    user_mode.pop(message.from_user.id, None)
    await message.answer("📍 Joylashuvingizni yuboring:", reply_markup=LOC_KB)


@dp.message(Command("route"))
@dp.message(F.text == "🗺️ Qayerga boraman?")
async def route(message: types.Message):
    uid = message.from_user.id
    if uid in user_loc:
        user_mode[uid] = "dest"
        await message.answer("🗺️ Qayerga borasiz? Manzil yoki joy nomini yozing (masalan: Chorsu bozori).")
    else:
        user_mode[uid] = "need_loc"
        await message.answer("Avval joylashuvingizni yuboring:", reply_markup=LOC_KB)


@dp.message(F.location)
async def on_location(message: types.Message):
    uid = message.from_user.id
    lat, lon = message.location.latitude, message.location.longitude
    user_loc[uid] = (lat, lon)
    if user_mode.get(uid) == "need_loc":
        user_mode[uid] = "dest"
        return await message.answer(
            "📍 Joylashuv olindi. Endi boradigan manzilni yozing (masalan: Chorsu bozori).",
            reply_markup=KB)
    await show_nearby(message, lat, lon)


@dp.message(F.text)
async def other_messages(message: types.Message):
    uid = message.from_user.id
    if user_mode.get(uid) == "dest" and uid in user_loc:
        user_mode.pop(uid, None)
        return await find_direct(message, user_loc[uid], message.text.strip())
    await message.answer(
        "🤖 Men Toshkent transport yordamchisiman.\n\n"
        "Tugmalardan birini tanlang yoki /start ni bosing.",
        reply_markup=KB,
    )


async def health(request):
    return web.Response(text="ok")


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000")))
    await site.start()


async def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN topilmadi")
    await start_health_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
