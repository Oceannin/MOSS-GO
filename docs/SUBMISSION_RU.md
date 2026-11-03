# Подача MOSS GO — 0.2.0-rc.1 / FLUX 3

[Официальные условия](https://comfy.org/open-source-higgsfield/) проверены
3 ноября 2026: дедлайн **3 ноября, 09:00 PST = 17:00 UTC = 22:00 Екатеринбурга**.
Остановить новые функции до 21:00. Старое упоминание 30 октября больше неактуально.

Заявку и соглашения отправляет автор. Если прежняя работа уже отправлена,
используйте ссылку изменения ответа или подтверждённый организаторами способ
обновления. Не создавайте вторую заявку: форма требует единственную submission.

## Ссылки

- [GitHub](https://github.com/Oceannin/MOSS-GO)
- [Релиз](https://github.com/Oceannin/MOSS-GO/releases/tag/v0.2.0-rc.1)
- [Демо](https://oceannin.github.io/MOSS-GO/)
- [Прямой MP4](https://oceannin.github.io/MOSS-GO/demo.mp4)
- [Установка](https://github.com/Oceannin/MOSS-GO/blob/main/docs/INSTALL.md)
- [Измерения](https://github.com/Oceannin/MOSS-GO/blob/main/docs/FLUX3_BENCHMARK.md)
- [Подача](https://form.typeform.com/to/V1dSQrkS)
- [Регистрация](https://form.typeform.com/to/Ayn9Cwfj)

Откройте ссылки без авторизации. Видео должно показывать FLUX 3 и длиться менее
двух минут. Поле **Live link** оставьте пустым: Pages показывает запись, генератор
работает локально. Локальный адрес не является live-сервисом для жюри.

## Готовые поля на английском

**Project name/title:** MOSS GO

**One-line description — меньше 100 символов:**

> Local FLUX 3 studio for character scenes, masked edits and reproducible ComfyUI workflows.

**GitHub repo URL:** https://github.com/Oceannin/MOSS-GO

**Demo video URL:** https://oceannin.github.io/MOSS-GO/demo.mp4

**Social post link:** ссылка на ваш опубликованный пост с видео и
`#OpenSourceHiggsfield`, не на профиль.

**Which parts of ComfyUI did you use?** — **Comfy API**. Не отмечайте SDK, Router,
Cloud Agent и Comfy MCP: приложение их не использует. Инструменты разработки
не становятся механизмами ComfyUI в runtime.

**List all generative models used:**

> Primary Create, Reference and Refine: FLUX 3 Image Klein distilled INT8 ConvRot, official Qwen3-VL 4B INT8 ConvRot encoder, official Qwen3.5 9B FLUX 3 prompt upsampler INT8 ConvRot, and the compatible FLUX VAE. All run locally through ComfyUI. Bundled original character anchors were generated with MOSS-Image SFT. Explicit legacy options include FLUX.2 Klein distilled 4B FP8 with Qwen3 4B, MOSS-Image SFT and experimental MOSS-Image CharRef LoRA. A separate optional Ollama Qwen3 4B Instruct 2507 assistant is not required or used by the demonstrated FLUX 3 path. Sources, hashes and separate licenses are documented.

**Other tools or techniques used:**

> A standalone Python/aiohttp studio with a local HTML/CSS/JavaScript interface over ComfyUI's API. FLUX 3 powers all three primary workflows using native image conditioning and actual image-aware local prompt upsampling. Our contribution is a durable workflow around those models: context-aware edit crops, source-coordinate feathered compositing, immutable execution snapshots plus observed expanded prompts, serial recoverable launches, related take history, and portable ZIP recipes with exact executed API graphs and inputs. Four evaluated edits preserved every pixel outside their effective masks. Export replay produced a pixel-identical image with no cached execution nodes. Tested on RTX 4070 Ti SUPER 16 GB / 32 GB RAM / Windows.

**Anything else you want the judges to know?**

> One character. Many scenes. Every detail under control. MOSS GO makes local ComfyUI image workflows usable without hiding how they ran. Start in English, choose an original reference, direct a scene, refine one selected detail, then keep the result together with its actual workflow. Our frozen 13-case FLUX 3 evaluation is published with all cases and limitations: 13 completed jobs, recognizable identity in 6/6 reference cases, requested action/pose in 5/6, and zero outside-mask pixel changes in all four local edits. We retain the failed walking case rather than replacing it with a showcase result. Other GPU sizes and Linux GPU execution remain unverified. Application code is Apache-2.0; FLUX 3 weights retain the separate FLUX Kommunity License. Setup, real examples, model checksums and reproducibility evidence are included.

## Категории

- **Best Overall** рассматривается автоматически.
- **Most Innovative**: отметьте и объясните в видео собственный вклад — точное
  локальное редактирование, фактические графы/промпты, переносимость и история.
- **Built with FLUX 3 Bonus**: отметьте; FLUX 3 теперь основной движок всех трёх
  сценариев и прошёл настоящие GPU-проверки.
- **Open Weights Only**: демонстрируемый путь использует локальные открытые веса,
  открытые узлы и зависимости, без partner nodes и closed model API. Источники
  четырёх компонентов проверены. Open weights не означает Apache: checkpoint
  имеет отдельную FLUX Kommunity License.
- **Is your stack fully open? — Yes** для описанного inference-стека. Не добавляйте
  закрытый API или непроверенную стороннюю LoRA в конкурсный critical path.
  Windows и NVIDIA driver — хост-платформа, а не заявление об открытости всех
  бинарников компьютера.
- LTX и MiniMax H3 не используются; соответствующие бонусы не отмечайте.

Окончательное решение за организаторами. Название модели не гарантирует награду.

## Социальный пост

> One character. Many scenes. Every detail under control.
>
> Built MOSS GO: a local FLUX 3 + ComfyUI studio for original characters, consistent scenes, precise masked edits and reproducible workflow recipes. Real outputs, published measurements and retained failures.
>
> https://github.com/Oceannin/MOSS-GO
> #OpenSourceHiggsfield

Прикрепите новое видео. Пост публикует автор; эта инструкция ничего не отправляет.

## Последние действия автора

1. Проверьте публичность repo, лицензию, установку, финальное видео и пост.
2. Самостоятельно заполните личные поля формы.
3. Прочитайте четыре соглашения: публичный лицензированный repo; lawful/SFW и
   права на IP/внешность; разрешение показа с авторством по Creator Feature Terms;
   единственная заявка. Подтверждайте только фактически верные положения.
4. Отправьте/обновите работу разрешённым способом до дедлайна.
5. Сохраните подтверждение, время, commit/tag и отправленные ссылки. Регистрация,
   черновик и GitHub сами по себе не означают отправленную конкурсную заявку.
