from PIL import Image, ImageFilter, ImageOps

# 1. Завантажуємо
img = Image.open('icon/metro_logo_without_border.png').convert("RGBA")

# 2. Налаштування (thickness — це кількість пікселів обводки)
thickness = 60

# 3. Створюємо полотно з великим запасом
padding = thickness + 10
new_size = (img.width + padding * 2, img.height + padding * 2)
canvas = Image.new("RGBA", new_size, (0, 0, 0, 0))
canvas.paste(img, (padding, padding))

# 4. Створюємо ЧІТКУ маску (без сильного розмиття)
mask = canvas.getchannel('A')

# Імітуємо розширення: зміщуємо маску в різні боки
# Це створює "жорстку" обводку без згладжування кутів
border_mask = Image.new("L", new_size, 0)
for x in range(-thickness, thickness + 1):
    for y in range(-thickness, thickness + 1):
        if x*x + y*y <= thickness*thickness: # Форма кола для обводки
            temp_mask = ImageOps.expand(mask, border=0) # Копія
            border_mask.paste(255, (x, y), mask=mask)

# 5. Створюємо білу підкладку
white_base = Image.new("RGBA", new_size, (255, 255, 255, 255))

# 6. Збираємо фінальний результат
final_img = Image.new("RGBA", new_size, (0, 0, 0, 0))
final_img.paste(white_base, (0, 0), mask=border_mask)
final_img.paste(canvas, (0, 0), mask=canvas)

# 7. Обрізаємо порожнечу
final_img = final_img.crop(final_img.getbbox())

# 8. Збереження
final_img.save('metro_logo.png')
final_img.show()
