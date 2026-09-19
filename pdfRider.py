import os
import asyncio
import shutil
import fitz  # PyMuPDF
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, FSInputFile, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = ''
bot = Bot(token=TOKEN)
dp = Dispatcher()

TEMP_DIR = "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

def get_conversion_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Получить .txt", callback_data="convert_text"))
    builder.row(InlineKeyboardButton(text="Получить изображения", callback_data="convert_image"))
    builder.row(InlineKeyboardButton(text="Закончить работу", callback_data="cancel"))
    return builder.as_markup()

def cpu_heavy_conversion(input_path, mode):
    doc = fitz.open(input_path)
    if mode == "text":
        text_path = input_path.replace(".pdf", ".txt")
        full_text = "".join([page.get_text() for page in doc])
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        doc.close()
        return text_path
    elif mode == "image":
        image_paths = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_path = f"{input_path}_{i}.png"
            pix.save(img_path)
            image_paths.append(img_path)
        doc.close()
        return image_paths

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Пришли мне PDF-файл")

@dp.message(F.document.mime_type == "application/pdf")
async def handle_pdf(message: types.Message):
    user_dir = os.path.join(TEMP_DIR, str(message.chat.id))
    os.makedirs(user_dir, exist_ok=True)
    
    file_path = os.path.join(user_dir, message.document.file_name)
    file = await bot.get_file(message.document.file_id)
    await bot.download_file(file.file_path, file_path)
    
    await message.answer(f"Файл <b>{message.document.file_name}</b> готов к работе. Что выберешь?", 
                         reply_markup=get_conversion_keyboard(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("convert_"))
async def process_conversion(callback: types.CallbackQuery):
    user_dir = os.path.join(TEMP_DIR, str(callback.message.chat.id))
    
    files = [f for f in os.listdir(user_dir) if f.endswith(".pdf")] if os.path.exists(user_dir) else []
    if not files:
        return await callback.answer("Файл не найден. Загрузи его снова.", show_alert=True)

    input_path = os.path.join(user_dir, files[0])
    status_msg = await callback.message.answer("⏳ Обрабатываю... Это может занять время.")
    
    loop = asyncio.get_event_loop()
    
    try:
        if callback.data == "convert_text":
            output_file = await loop.run_in_executor(None, cpu_heavy_conversion, input_path, "text")
            await callback.message.answer_document(FSInputFile(output_file), caption="текст готов.")
            os.remove(output_file)

        elif callback.data == "convert_image":
            images = await loop.run_in_executor(None, cpu_heavy_conversion, input_path, "image")
            for i in range(0, len(images), 10):
                chunk = images[i:i + 10]
                media = [InputMediaPhoto(media=FSInputFile(path)) for path in chunk]
                await callback.message.answer_media_group(media=media)
            for path in images: os.remove(path)

    except Exception as e:
        await callback.message.answer(f"ошибка: {e}")
    finally:
        await status_msg.delete()
        await callback.message.answer("Что-нибудь еще сделать с этим файлом?", 
                                      reply_markup=get_conversion_keyboard())
        await callback.answer()

@dp.callback_query(F.data == "cancel")
async def cancel_handler(callback: types.CallbackQuery):
    user_dir = os.path.join(TEMP_DIR, str(callback.message.chat.id))
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir)
    
    await callback.message.edit_text("Жду нового файла")
    await callback.answer()

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
