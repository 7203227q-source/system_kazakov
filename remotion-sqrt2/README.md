# Remotion: √2 с растущей полочкой

Композиция: `Sqrt2Pole`

## Запуск

```bash
cd remotion-sqrt2
npm i
npm run studio
```

## Рендер

```bash
cd remotion-sqrt2
npm i
npm run render
```

## Chrome

Для запуска Studio и рендера Remotion нужен Chrome/Chromium. Если авто-скачивание браузера недоступно в окружении, укажите путь к установленному браузеру:

```bash
npx remotion render src/index.ts Sqrt2Pole out/sqrt2-pole.mp4 --overwrite --browser-executable=/path/to/chrome
```
