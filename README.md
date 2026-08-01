# Video2Zip

macOS için **tamamen yerel** çalışan video → kare (frame) dönüştürücü.
Bir videonun her karesini ayrı görsel dosyasına çevirir ve hepsini tek bir ZIP
arşivinde toplar. Tarayıcı yok, sunucu yok, dosya yükleme yok — videonuz
Mac'inizden hiç çıkmaz.

```
Video seç → biçim + ayarlar → kareleri çıkar → ZIP olarak kaydet
```

---

## Kurulum

### 1. Tkinter'ı hazırlayın (bir kereye mahsus)

Homebrew Python'unda Tkinter ayrı bir paket olarak gelir:

```bash
brew install python-tk@3.14
```

> Farklı bir sürüm kullanıyorsanız numarayı ona göre değiştirin
> (`python3 -V` ile bakabilirsiniz). Alternatif olarak
> [python.org](https://www.python.org/downloads/macos/) yükleyicisini
> kurabilirsiniz — Tcl/Tk dahili gelir.
>
> **Not:** macOS'un `/usr/bin/python3` içindeki Tk 8.5 çok eski ve modern
> macOS'ta pencere çizerken kilitlenir. Homebrew ya da python.org kurulumu
> (Tk 8.6+) kullanın.

### 2. Bağımlılıkları kurun

```bash
cd Video2Zip && ./setup.sh
```

`setup.sh` sanal ortam (`.venv`) açar ve `requirements.txt` içindekileri kurar:
`opencv-python`, `customtkinter`, `Pillow`.

### 3. Çalıştırın

```bash
cd Video2Zip && ./run.sh
```

Elle çalıştırmak isterseniz:

```bash
cd Video2Zip && ./.venv/bin/python main.py
```

İlk çalıştırmadan önce betiklere çalıştırma izni gerekebilir:

```bash
chmod +x setup.sh run.sh
```

---

## Uygulama olarak kurma (.app)

Terminal'e hiç girmeden, normal bir Mac uygulaması gibi kullanmak için:

```bash
cd Video2Zip && ./build_app.sh
```

Bu, `Video2Zip.app` üretir (~166 MB) — kendi Python kütüphanelerini içinde
taşır, proje klasörü silinse bile çalışır. Uygulamalar klasörüne taşımak için:

```bash
cp -R Video2Zip.app /Applications/
```

Paket ad-hoc imzalanır; Apple Developer hesabı gerekmez. Kendi ürettiğiniz
uygulama olduğu için Gatekeeper uyarısı çıkmaz, ama çıkarsa uygulamaya sağ
tıklayıp **Aç** demek yeterlidir (bir kereye mahsus).

Paket ne içerir:

```
Video2Zip.app/Contents/
├── Info.plist              # ad, ikon, açabildiği dosya türleri
├── MacOS/
│   ├── launch              # başlatıcı (CFBundleExecutable)
│   └── Video2Zip           # Python.framework'ün GUI ikilisi, uygulama adıyla
└── Resources/
    ├── AppIcon.icns
    ├── app/                # main.py + video2zip/
    └── lib/                # opencv, customtkinter, Pillow, tkinterdnd2
```

> **Neden ikili `Video2Zip` adını taşıyor?** `venv/bin/python` yalnızca bir
> sapdır (stub); çalışınca kendini `Python.framework`'e devreder ve macOS
> uygulamayı "Python" olarak listeler — Dock'ta yanlış ad ve genel ikon
> görünür. Framework'ün GUI ikilisi doğrudan `Contents/MacOS/` içine, uygulama
> adıyla kopyalandığında süreç paketin içinde kalır ve macOS onu `Video2Zip`
> olarak tanır.

Uygulama `public.movie` türlerini de kaydeder: Finder'da bir videoya sağ tıklayıp
**Bununla Aç → Video2Zip** diyebilir ya da videoyu Dock ikonunun üstüne
bırakabilirsiniz — dosya doğrudan yüklenir.

---

## Proje yapısı

```
Video2Zip/
├── main.py                 # giriş noktası
├── requirements.txt
├── setup.sh                # sanal ortam + bağımlılık kurulumu
├── run.sh                  # uygulamayı başlatır
├── build_app.sh            # bağımsız Video2Zip.app üretir
├── assets/
│   ├── make_icon.py        # uygulama ikonunu üretir (squircle + gradyan)
│   ├── AppIcon.png         # 1024×1024 kaynak
│   └── AppIcon.icns        # paket ikonu
└── video2zip/
    ├── __init__.py
    ├── theme.py            # tasarım token'ları — her renk (açık, koyu) çifti
    ├── icons.py            # SF Symbols tarzı, Pillow ile çizilen vektör ikonlar
    ├── prefs.py            # kalıcı tercihler (tema, son biçim)
    ├── extractor.py        # OpenCV motoru — Tk bağımlılığı yok, ayrı thread
    └── app.py              # CustomTkinter arayüzü
```

Mimari ayrım bilinçli: `extractor.py` saf işlem katmanı (test edilebilir,
arayüzden bağımsız), `app.py` ise yalnızca sunum ve durum yönetimi yapar.
İkisi arasındaki tek köprü bir `queue.Queue` — worker thread olayları kuyruğa
yazar, arayüz `after()` ile 60 ms'de bir kuyruğu boşaltır. Bu yüzden uzun
işlemler sırasında pencere **hiç donmaz**.

---

## Özellikler

| Özellik | Açıklama |
|---|---|
| **Görsel biçimi** | PNG, JPG, WEBP, BMP, TIFF (açılır menü) |
| **Kalite / sıkıştırma** | JPG & WEBP için kalite, PNG için sıkıştırma seviyesi. BMP/TIFF'te otomatik devre dışı |
| **Ölçek** | %10–%200 arası yeniden boyutlandırma; küçültmede `INTER_AREA`, büyütmede `INTER_CUBIC` |
| **Kare aralığı** | Her kareyi ya da her N. kareyi al (1–30) |
| **Zaman aralığı** | Videonun sadece belirli bir saniye aralığını işle |
| **Dosya adı ön eki** | `frame_0001.png`, `kare_0001.jpg` … sıfır dolgulu, sıralaması asla bozulmaz |
| **Canlı tahmin** | Ayarları değiştirdikçe "kaç kare çıkacak" anında güncellenir |
| **İlerleme** | Yüzde + progress bar + kare/sn hızı + kalan süre tahmini |
| **İptal** | İşlem ortasında durdurma; geçici dosyalar otomatik temizlenir |
| **ZIP + Kaydet As** | Bitince macOS'un yerel kaydetme penceresi açılır; iptal ederseniz arşiv beklemede kalır ve tekrar deneyebilirsiniz |
| **Finder'da göster** | Kaydedilen ZIP'i tek tıkla Finder'da açar |
| **Açık / Koyu mod** | Başlıktaki güneş-ay ikonuyla anında geçiş; tercih kalıcı |
| **Sürükle-bırak** | Videoyu pencerenin herhangi bir yerine bırakmak yeterli; bırakma sırasında kart vurgulanır |

---

## Tasarım

Amaç, Tk ile yazılmış bir uygulamanın native macOS uygulaması gibi
görünmesi ve davranması:

- **Sistem renkleri**, marka paleti yok. `theme.py` içindeki her token bir
  `(açık, koyu)` çifti (`labelColor`, `secondaryLabelColor`, `separatorColor`,
  `controlAccentColor` karşılıkları). CustomTkinter appearance mode değişince
  doğru olanı kendisi seçer — tek satır geçiş kodu yok.
- **Sistem tipografisi**: `.AppleSystemUIFont`, `TkDefaultFont`'un bildirdiği
  boyuttan türetilen ölçek (headline / body / callout / caption). Kullanıcının
  sistem metin boyutu ayarına uyar.
- **İnce ayırıcılar ve satır tabanlı form**: başlık → ayırıcı → bölümler →
  ayırıcı → alt şerit. Kartlar `radius 8`, `1px` kenarlık.
- **İkonlar** SF Symbols tarzında (1.6px stroke, yuvarlak uç) Pillow ile 4x
  çizilip küçültülür; her ikon açık ve koyu varyantıyla birlikte üretilir.
- **Vurgu rengi** yalnızca ana butonda ve ilerleme çubuğunda kullanılır;
  geri kalan her şey gri tonlarında.
- **Hafif saydamlık** (`-alpha 0.95`) — sistem panellerinin materyal hissine
  yaklaşmak için. Tk gerçek vibrancy/blur sunmadığından pencere opaklığı
  kullanılır; değer `app.py` içindeki `WINDOW_ALPHA` sabitinden ayarlanabilir.

Menü bar uygulaması değil — kendi penceresi olan normal bir masaüstü
uygulaması, Dock'ta görünür.

### Uygulama ikonu

`assets/make_icon.py` ikonu kodla üretir, macOS Big Sur+ şablonuna uyar:

- 1024×1024 tuval, görsel alan ortada **824×824**
- Apple'ın **squircle** formu — PIL'in dairesel köşesi değil, süperelips
  (`|x/a|ⁿ + |y/b|ⁿ ≤ 1`, n = 5) maskesiyle çizilir
- systemBlue → systemIndigo diyagonal gradyan, üstte yumuşak ışık, altta gölge
- Tek beyaz sembol: film şeridi + aşağı ok + arşiv tepsisi

Değiştirmek için `make_icon.py`'yi düzenleyip çalıştırın, sonra
`./build_app.sh` ile paketi yeniden üretin:

```bash
./.venv/bin/python assets/make_icon.py
```

### Kısayollar

| Tuş | İşlev |
|---|---|
| `⌘O` | Video seç |
| `⌘↩` | İşlemi başlat / ZIP'i kaydet |

---

## Nasıl çalışır

1. **Sondaj** — `cv2.VideoCapture` ile çözünürlük, FPS, kare sayısı ve süre okunur.
2. **Çıkarma** — Kareler sırayla okunur. Atlanacak kareler için `grab()`
   kullanılır (çözme maliyeti olmadan ilerler), yalnızca kaydedilecek kareler
   `retrieve()` ile çözülür — kare aralığı > 1 iken belirgin hız kazancı.
3. **Yazma** — `cv2.imencode` + `open(..., "wb")` ikilisi kullanılır; böylece
   Türkçe karakterli dosya adlarında kodlama sorunu çıkmaz.
4. **Arşivleme** — Kareler geçici klasörde toplanır, ardından ZIP'e alınır.
   PNG/JPG/WEBP zaten sıkıştırılmış olduğu için `ZIP_STORED`, BMP/TIFF için
   `ZIP_DEFLATED` kullanılır.
5. **Kaydetme** — Yerel "Farklı Kaydet" penceresi açılır, arşiv seçtiğiniz
   konuma taşınır, geçici klasör silinir.

---

## Sorun giderme

**`ModuleNotFoundError: No module named '_tkinter'`**
Tkinter kurulu değil → `brew install python-tk@3.14`

**Pencere açılıyor ama donuyor / çizim yapmıyor**
Muhtemelen Apple'ın `/usr/bin/python3` (Tk 8.5) kullanılıyor. `setup.sh`'ı
Homebrew veya python.org Python'u ile çalıştırın:
`PYTHON=/opt/homebrew/bin/python3.14 ./setup.sh`

**"Toplam kare: bilinmiyor"**
Bazı konteynerler kare sayısını bildirmez. İşlem yine çalışır, sadece yüzde
göstergesi yerine sayaç ilerler.

**Video açılamıyor**
OpenCV kendi codec setini kullanır; egzotik codec'lerde
`ffmpeg -i girdi.mov -c:v libx264 cikti.mp4` ile dönüştürüp tekrar deneyin.

---

## Test

Motor katmanı arayüzden bağımsız test edilebilir:

```python
from video2zip.extractor import probe_video, ExtractOptions, ExtractionJob
import queue

info = probe_video("video.mp4")
q = queue.Queue()
job = ExtractionJob(info, ExtractOptions(fmt="JPG", quality=90, step=5), q)
job.start(); job.join()
print(q.queue[-1])   # {'type': 'done', 'zip_path': ...}
```
