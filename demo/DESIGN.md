# MagicPay SDK demo mağazası: tasarım planı

Bu belge `demo/` uygulamasının (Jinja2 + az vanilla JS, build yok) görsel ve metin spesifikasyonudur.
Bağlayıcı kural kaynağı: `~/.claude/docs/design/ui-rules.md`. Bu belgede olmayan bir karar
gerekirse yeni renk, font ya da boşluk değeri uydurmayın; aşağıdaki token'lardan birini kullanın.

---

## 1. Yön ve akılda kalan unsur

Ekran ikiye ayrılır. Solda müşterinin gördüğü sade bir mağaza vitrini, sağda **"sunucu fiş
rulosu"**: sunucudaki SDK'nın MagicPay'e yaptığı her çağrı, POS cihazından çıkan bir slip gibi
rulonun en üstüne basılır. Türkiye'de kartla ödeme yapan herkes POS slipini tanır; bu yüzden
geliştirici de işletme tarafındaki izleyici de sağ paneli açıklamaya gerek kalmadan "arka
planda olan kayıt" diye okur. Rulo, soğuk tonlu termal kâğıt renginde tek ve kesintisiz bir
yüzeydir. Kart kutuları, gölge ve köşe yuvarlatma kullanılmaz. Kayıtlar birbirinden kesik
"yırtma çizgisi" ile ayrılır, panelin üstünde koyu mürekkep renginde bir "yazıcı ağzı" bulunur.
**Tek akılda kalan unsur bu rulo ve onun tek planlı anıdır:** yeni bir çağrı geldiğinde satır
yazıcı ağzının altından aşağı doğru çıkar ve kısa süre fosforlu kalem sarısıyla işaretli kalır.
Mağaza tarafı bilerek sakin tutulur: beyaz zemin, mürekkep rengi metin, tek bir dolu buton.
Bütün cesaret sağ panelde harcanır.

Font seçimi de konudan gelir. Video sıkıştırmasında ve 1080p kayıtta `0/O`, `1/l/I` ve Türkçede
kritik olan `ı/i/İ` ayrımı kaybolmamalı. Ödeme no, sipariş no, BIN ve kart numarası bu
karakterlerle dolu. Bu nedenle okunurluk için tasarlanmış **Atkinson Hyperlegible** ailesi
seçildi: arayüz için **Next**, JSON ve kod tanımlayıcıları için aynı ailenin **Mono**
üyesi kullanılır.

---

## 2. Token'lar (CSS custom properties)

Aşağıdaki bloğu olduğu gibi `demo/static/css/tokens.css` dosyasına koyun ve diğer CSS'te
yalnızca bu değişkenleri kullanın. Hex değeri doğrudan yazmayın.

### 2.1 Font yükleme (Google Fonts)

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;600;700&family=Atkinson+Hyperlegible+Mono:wght@400;600&display=swap">
```

İlk kurulumda şu test dizesiyle Türkçe glifleri kontrol edin: `ğüşıöçİĞÜŞÖÇ 0O 1lI`.
Mono tarafında eksik glif çıkarsa fallback yığını devreye girer. Bu kabul edilebilir, font
değiştirmeyin.

### 2.2 Değişkenler

```css
:root {
  /* ---- Temel palet (6) ---- */
  --color-murekkep: #1C2B45;  /* Mürekkep: gövde metni, başlıklar, birincil buton zemini, yazıcı ağzı. Beyazda 14:1 */
  --color-kagit:    #FFFFFF;  /* Kâğıt: mağaza yüzeyi, form alanı zemini */
  --color-rulo:     #EEF2F5;  /* Rulo: SDK kaydı panelinin termal kâğıt zemini */
  --color-kenar:    #7A8594;  /* Kenar: input, radio ve ikincil buton kenarı. Beyazda 3.7:1 (WCAG 1.4.11) */
  --color-onay:     #1D6B3A;  /* Onay: başarılı durum metni. Beyazda 6.5:1 */
  --color-ret:      #B42318;  /* Ret: hata metni, hata kenarı, iade onay butonu zemini. Beyazda 6.5:1 */

  /* ---- İşlevsel ek renkler (paletin parçası değil, yalnızca belirtilen rol için) ---- */
  --color-murekkep-2:  #2E4066; /* birincil buton hover, yazıcı ağzının alt dudağı */
  --color-soluk:       #4F5B6B; /* ikincil metin. Beyazda 7:1, rulo üstünde 6.3:1 */
  --color-cizgi:       #C9D1DA; /* tablo satır çizgileri, iki sütun arasındaki dikiş. Bilgi taşımayan ayraç */
  --color-yirtma:      #9AA5B1; /* rulodaki kesik yırtma çizgisi */
  --color-agiz-metin:  #C9D2DE; /* yazıcı ağzındaki ikincil metin. Mürekkep üstünde 9:1 */
  --color-secim:       #E4EBF5; /* seçili taksit satırı zemini */
  --color-odak:        #2B63D9; /* klavye odak halkası. Beyazda 5.4:1, rulo üstünde 4.8:1 */
  --color-fosfor:      #FFF0B3; /* yeni gelen kayıt satırının geçici işareti */
  --color-onay-zemin:  #E6F2E9; /* "Başarılı" etiketinin zemini */
  --color-ret-zemin:   #FBEAE8; /* hata satırı ve "Başarısız" etiketi zemini. Ret metni üstünde 5.6:1 */
  --color-bekleme:     #7A4D00; /* bekleyen durum metni, test ortamı etiketi metni. Beyazda 7.3:1 */
  --color-bekleme-zemin: #FCF1D0; /* test ortamı etiketi ve "3D bekleniyor" etiketinin zemini */

  /* ---- Fontlar ---- */
  --font-arayuz: "Atkinson Hyperlegible Next", "Segoe UI", system-ui, sans-serif;
  --font-kod:    "Atkinson Hyperlegible Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
  /* Mono YALNIZCA şuralarda: SDK metot adı, HTTP metodu + path, JSON blokları.
     Tutar, süre, HTTP durumu, saat, ödeme no ve sipariş no arayüz fontuyla ve tabular rakamla yazılır. */
  --num: tabular-nums;          /* font-variant-numeric: var(--num); tüm tutar, no, süre, saat */

  /* ---- Tip ölçeği (rem, kök 16px; >=1800px'te kök %106.25) ---- */
  --fs-1: 0.875rem;   /* 14px: tablo başlığı, açıklama, rulo ikincil satırı, JSON. Kayıttaki en küçük boyut */
  --fs-2: 0.9375rem;  /* 15px: form etiketi, rulodaki path satırı, durum etiketi */
  --fs-3: 1.0625rem;  /* 17px: gövde, input içeriği, buton, rulodaki SDK metot adı */
  --fs-4: 1.3125rem;  /* 21px: bölüm başlığı (h2) */
  --fs-5: 1.75rem;    /* 28px: sayfa başlığı (h1), ödenecek tutar */
  --fs-6: 2.5rem;     /* 40px: ürün fiyatı ve sonuç sayfasındaki tutar */
  --lh-siki: 1.2;     /* fs-5, fs-6 */
  --lh-orta: 1.35;    /* fs-4, butonlar, rulo özet satırları */
  --lh-govde: 1.5;    /* gövde ve JSON */
  --fw-normal: 400;
  --fw-vurgu: 600;    /* etiket, SDK metot adı, seçili satır, buton */
  --fw-guclu: 700;    /* yalnızca h1, fiyat, hata satırındaki HTTP durumu */

  /* ---- Boşluk (4'lük) ---- */
  --space-1: 4px;   --space-2: 8px;   --space-3: 12px;  --space-4: 16px;
  --space-5: 24px;  --space-6: 32px;  --space-7: 48px;  --space-8: 64px;

  /* ---- Köşe (hiyerarşiye göre, hepsi aynı değil) ---- */
  --radius-kontrol: 6px; /* input, buton, taksit tablosunun dış çerçevesi */
  --radius-etiket: 3px;  /* durum etiketi, test ortamı etiketi */
  --radius-yok: 0;       /* rulo, kayıt satırı, JSON bloğu, sipariş tablosu, demo ayarı kutusu */

  /* ---- Kenarlar ---- */
  --border-kontrol: 1px solid var(--color-kenar);
  --border-cizgi:   1px solid var(--color-cizgi);
  --border-yirtma:  1px dashed var(--color-yirtma);
  --border-demo:    1px dashed var(--color-kenar);    /* "bu mağazanın parçası değil, sunucunun ayarı" */
  --border-agiz:    3px solid var(--color-murekkep-2); /* yazıcı ağzının alt dudağı */
  --odak-halkasi:   2px solid var(--color-odak);      /* outline; offset 2px */

  /* ---- Yerleşim ---- */
  --header-h: 64px;
  --log-w: 400px;          /* 900-1279px */
  --icerik-max: 800px;
  --kontrol-h: 48px;       /* input ve birincil buton */
  --kontrol-h-kucuk: 36px; /* tablo içi butonlar */

  /* ---- Hareket ---- */
  --sure-tepki: 120ms;     /* hover, chevron dönüşü */
  --sure-besleme: 240ms;   /* yeni kayıt satırının yazıcıdan çıkışı */
  --sure-fosfor: 1800ms;   /* fosfor işaretinin toplam süresi (600ms sabit + 1200ms sönme) */
  --egri-besleme: cubic-bezier(.2, .7, .3, 1);
}

@media (min-width: 1280px) { :root { --log-w: 560px; } }
@media (min-width: 1800px) { :root { --log-w: 760px; --icerik-max: 880px; font-size: 106.25%; } }
```

Gölge token'ı yoktur. Arayüzün hiçbir yerinde `box-shadow` kullanılmaz (odak halkası `outline`
ile yapılır).

---

## 3. Yerleşim ızgarası

### 3.1 Masaüstü (1440 ve 1920, kayıt hedefi)

Sayfa iki sütunlu bir CSS grid'dir: `grid-template-columns: minmax(0, 1fr) var(--log-w)`.
Sütunlar arasında `--border-cizgi` ile 1px dikiş çizgisi bulunur. Header da aynı dikişten
bölünür: sağ parçası rulonun tam üstüne denk gelir ve sunucu tarafı bilgisini (test ortamı)
taşır. Sunucuya ait bilgi böylece sunucu panelinin üstünde durur.

| Genişlik | Ana sütun | Rulo (`--log-w`) | İçerik max | Ana sütun yatay padding |
|---|---|---|---|---|
| 1440 | 880px | 560px | 800px, ortalı | `--space-5` (40px'e kadar boşluk kalır) |
| 1920 | 1160px | 760px | 880px, ortalı | `--space-8` |
| 900–1279 | kalan | 400px | 800px | `--space-5` |

- Rulo `position: sticky; top: var(--header-h); height: calc(100vh - var(--header-h))` ile
  sabit kalır. Kendi içinde kaydırılır, sayfa kaydırılınca yerinden oynamaz.
- Hizalama: tüm metin sola hizalı. Tutar, süre ve no sütunları sağa hizalıdır, tabular rakam.
- Kayıt önerisi: tarayıcı tam ekran (F11), 1920×1080. Mağaza ekranı bu yükseklikte
  kaydırmadan sığacak şekilde tasarlandı (bkz. 4.1).

```
1920 x 1080
+------------------------------------------------------------+----------------------------------+
| Kalaycı Bakır   Mağaza  Siparişler  Bağlantı kontrolü      | [Test ortamı (trdev.magicpay.ai)]|  64px header
+------------------------------------------------------------+----------------------------------+
|                                                            |##### YAZICI AĞZI (mürekkep) #####|
|          +-------------- içerik 880 --------------+        | SDK çağrıları   7 çağrı  [Temizle]|
|          |                                        |        | Sunucunuzdaki SDK'nın istekleri.. |
|          |   (sayfa içeriği)                      |        |==================================|
|          |                                        |        | rulo: kayıt satırları            |
|          +----------------------------------------+        | - - - - - - - - - - - - - - - - -|
|                                                            | kayıt satırı                     |
|                                                            | - - - - - - - - - - - - - - - - -|
+------------------------------------------------------------+----------------------------------+
                      ana sütun 1160                                   rulo 760
```

### 3.2 Mobil (375)

- Tek sütun, yatay padding `--space-4`. Yatay taşma yoktur. Uzun path ve JSON satırları
  kırılır (`overflow-wrap: anywhere`).
- Header iki satırdır: 1. satırda mağaza adı ve sağda test ortamı etiketi
  (`Test ortamı` kısa biçimi, `title` ile tam adres), 2. satırda üç nav linki.
- Rulo içeriğin **altına** iner ve varsayılan olarak kapalıdır. Yapısı 6.4'te.
- Sayfanın en başında, odaklanınca görünen bir atlama linki bulunur: `SDK çağrılarına atla`.

```
375
+-----------------------------------+
| Kalaycı Bakır      [Test ortamı]  |
| Mağaza  Siparişler  Bağlantı kont.|
+-----------------------------------+
| içerik (tek sütun)                |
| ...                               |
+-----------------------------------+
|#### SDK çağrıları (7)   Göster ###|  48px, yazıcı ağzı = açma düğmesi
| Son çağrı: payments.init_3ds_...  |
+-----------------------------------+
```

---

## 4. Ekranlar

### 4.1 Mağaza / ödeme (`/`)

```
içerik 800 (1440)
+--------------------------------------------------------------------------+
| Bakır cezve, 2 fincanlık  (h1, fs-5)                    1.250,00 TL (fs-6)|
| Gaziantep'te elde dövülmüş, içi kalaylı bakır cezve. Ahşap saplı, 250 ml. |
|                                                                          |
| +- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+ |
| ' Demo ayarı: ödeme tutarı  [ 1.250,00 ] TL  [Tutarı uygula]            ' |
| ' Taksit tablosu yeni tutara göre yeniden hesaplanır.                   ' |
| +- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+ |
|                                                                          |
| Kart bilgileri (h2)                  | Taksit seçimi (h2)                 |
| Kart alanları EsnekPOS test kartıyla | +--------------------------------+ |
| dolduruldu. Gerçek kart girmeyin.    | |   Taksit      Aylık      Toplam| |
|                                      | |(o) Tek çekim 1.250,00  1.250,00| |
| Kart numarası                        | |( ) 2 taksit    637,50  1.275,00| |
| [ 4155 6500 0000 0012            ]   | |( ) 3 taksit    429,00  1.287,00| |
| Halkbank kredi kartı (Visa)          | |  ...                           | |
|                                      | +--------------------------------+ |
| Kart üzerindeki isim                 | Fiyatlar, mağazanın POS'ları       |
| [ Test Kullanıcı                 ]   | arasındaki en düşük müşteri        |
|                                      | fiyatıdır.                         |
| Son kullanma tarihi  Güvenlik kodu   |                                    |
| [ 12/30        ]     [ 000 ]         |                                    |
|--------------------------------------------------------------------------|
| Ödenecek tutar                                                           |
| 1.287,00 TL (fs-5)                         [ 3 taksitle 1.287,00 TL öde ]|
| 3 taksit, aylık 429,00 TL                  Ödemeyi bankanızın 3D Secure  |
|                                            sayfasında onaylayacaksınız.  |
+--------------------------------------------------------------------------+
```

Dikey bütçe (1080p): header 64, üst boşluk 32, ürün ~110, demo kutusu ~72, boşluk 32,
form/taksit ~400, ödeme çubuğu ~110. Toplam ~ 820px, kaydırma gerekmez.

**Ürün bloğu.** h1 solda, fiyat aynı satırda sağda (`--fs-6`, `--fw-guclu`, tabular).
Açıklama `--fs-3`, `--color-soluk`, max 60ch. Görsel yok. Yer tutucu görsel koymayın.
Fiyat demo ayarındaki tutarı gösterir.

**Demo ayarı kutusu.** `--border-demo`, `--radius-yok`, padding `--space-3 --space-4`, zemin
şeffaf. Kesik kenar bunun mağazanın değil sunum yapanın kontrolü olduğunu söyler.
- Etiket (`<label>`): `Demo ayarı: ödeme tutarı`
- Input: genişlik 160px, sağa hizalı, tabular. Virgüllü ondalık kabul eder (`1250`, `1250,5`,
  `1.250,50`). Sağında düz metin `TL`.
- Buton (ikincil, küçük): `Tutarı uygula`. Basınca `installments.list_checkout_installments`
  yeniden çağrılır, fiyat, taksit tablosu ve ödeme çubuğu güncellenir.
- Yardım metni (`--fs-1`, soluk): `Taksit tablosu yeni tutara göre yeniden hesaplanır.`
- Hata: `Tutarı 1,00 TL ile 50.000,00 TL arasında girin.` (sınırlar config'den gelir)

**Kart formu.** Etiketler input'un üstünde, `--fs-2`, `--fw-vurgu`, cümle düzeninde.
Input: yükseklik `--kontrol-h`, `--fs-3`, padding `0 var(--space-3)`, `--border-kontrol`,
`--radius-kontrol`, zemin kâğıt. Alanlar arası `--space-4`.

| Alan | Etiket | Özellikler | Hata metni |
|---|---|---|---|
| Kart numarası | `Kart numarası` | `inputmode=numeric`, `autocomplete=cc-number`, 4'lü gruplar boşlukla, tam genişlik | `Kart numarası 16 hane olmalı. Eksik haneleri tamamlayın.` |
| İsim | `Kart üzerindeki isim` | `autocomplete=cc-name`, tam genişlik | `Kart üzerindeki ismi girin.` |
| Son kullanma | `Son kullanma tarihi` | tek alan `AA/YY`, `autocomplete=cc-exp`, placeholder `AA/YY` | `Son kullanma tarihini AA/YY biçiminde girin, örneğin 12/30.` ya da `Bu kartın süresi dolmuş. Kartın üzerindeki tarihi girin.` |
| CVC | `Güvenlik kodu` | 3 hane, `autocomplete=cc-csc`, genişlik 120px | `Güvenlik kodu kartın arkasındaki 3 hanedir.` |

- Form başında açıklama (`--fs-1`, soluk): `Kart alanları EsnekPOS test kartıyla dolduruldu.
  Gerçek kart bilgisi girmeyin.` Değerler config'den gelir. Belgeye kart numarası yazılmadı.
- Hata durumu: input kenarı `--color-ret`, altında `--fs-1` ret rengi metin,
  `aria-describedby` ile bağlı, `aria-invalid="true"`. Yalnızca renk değil metin de var.
- Doğrulama blur'da ve submit'te çalışır, yazarken çalışmaz.

**BIN satırı** (kart numarası input'unun hemen altında, `--fs-2`, `aria-live="polite"`).
İlk 6 hane girildiği anda bir kez sorgu atılır. 6 hane değişmedikçe tekrar sorgulanmaz.
Sayfa açılışında test kartı dolu geldiği için ilk sorgu sayfa yüklenince gider.

| Durum | Metin | Renk |
|---|---|---|
| 6 haneden az | `Kartın bankası ilk 6 haneden bulunur.` | soluk |
| Sorgulanıyor | `Kart bilgisi sorgulanıyor…` | soluk |
| Bulundu | `{banka} {kart tipi} kartı ({şema})`, örn. `Halkbank kredi kartı (Visa)` | mürekkep, banka adı `--fw-vurgu` |
| Bulunamadı | `Bu kartın bankası bulunamadı. Numarayı kontrol edin; ödeme yine de denenebilir.` | soluk |
| Hata | `Kart bilgisi alınamadı. Ödemeye devam edebilirsiniz.` | soluk |

Kart tipi eşlemesi: `CREDIT` → `kredi`, `DEBIT` → `banka`, `PREPAID` → `ön ödemeli`. Şema
olduğu gibi yazılır (Visa, Mastercard, Troy, Amex). Logo kullanılmaz.

**Taksit tablosu.** Kaynak `installments.list_checkout_installments(amount, currency=TRY)`.
- Gerçek `<table>`. Dış çerçeve `--border-kontrol` + `--radius-kontrol` (`overflow: hidden`),
  satır araları `--border-cizgi`. Başlık satırı: `Taksit`, `Aylık`, `Toplam`. `--fs-1`,
  `--fw-vurgu`, soluk, cümle düzeninde (büyük harf yok).
- Her satır bir `<label>` ile kaplı radio'dur. Satırın tamamı tıklanır, yükseklik 44px.
  Radio 20px, `accent-color: var(--color-murekkep)`.
- Satır metni: `Tek çekim`, `2 taksit`, `3 taksit`… Tutarlar `1.250,00 TL` biçiminde, sağa
  hizalı, tabular.
- Seçili satır: zemin `--color-secim`, metin `--fw-vurgu`. Hover: zemin `--color-rulo`
  (yalnızca renk, büyüme yok).
- Varsayılan seçim: `Tek çekim`.
- Tablo altı not (`--fs-1`, soluk): `Fiyatlar, mağazanın POS'ları arasındaki en düşük müşteri
  fiyatıdır.`
- Durumlar:
  - Yükleniyor: tablo gövdesi yerine tek satır `Taksit seçenekleri getiriliyor…`
  - Yalnızca tek çekim: tablo tek satır ve altında `Bu tutar için taksit seçeneği yok; ödeme
    tek çekim alınır.`
  - Hata: tek satır `Tek çekim` (tutar = demo tutarı) ve üstünde ret renginde `Taksit
    seçenekleri alınamadı. Tek çekim ödeyebilir ya da tutarı yeniden uygulayarak tekrar
    deneyebilirsiniz.`

**Ödeme çubuğu.** Üstünde `--border-cizgi`, padding-top `--space-5`. Solda: `Ödenecek tutar`
(`--fs-2`, soluk), altında toplam (`--fs-5`, `--fw-guclu`), altında taksit özeti
(`Tek çekim` ya da `3 taksit, aylık 429,00 TL`). Sağda birincil buton (min genişlik 320px),
altında `--fs-1` soluk not.
- Buton metni seçime göre değişir: `1.250,00 TL öde` / `3 taksitle 1.287,00 TL öde`.
- Basılınca: buton devre dışı, metin `Ödeme başlatılıyor…`. Form gönderilir, sunucu
  `payments.init_3ds_payment` çağırır.
- Not: `Ödemeyi bankanızın 3D Secure sayfasında onaylayacaksınız.`

### 4.2 Bankaya yönlendirme (ara ekran, `/odeme/yonlendir`)

Ara ekran **kullanılır**. Bu ekran rulodaki `payments.init_3ds_payment` kaydını anlatmak için
sunucuya zaman tanır. Otomatik yönlendirme yoktur, sunum yapan kişi butona basar.

```
| Banka doğrulaması (h1)                                         |
| Ödemeyi onaylamak için bankanızın 3D Secure sayfasına           |
| geçiyorsunuz. Orada telefonunuza gelen kodu gireceksiniz.       |
|                                                                 |
| Tutar        1.287,00 TL                                        |
| Taksit       3 taksit, aylık 429,00 TL                          |
| Kart         415565******0012 (Halkbank)                        |
|                                                                 |
| [ Banka sayfasına geç ]   Ödemeden vazgeç (link)                |
| Banka sayfası bankanın kendi tasarımıdır; bu mağazaya ait değil.|
```

- Bilgiler `<dl>`. Terimler soluk `--fs-2`, değerler mürekkep `--fs-3` tabular. Terim sütunu
  160px.
- `Banka sayfasına geç`: bankanın HTML'ini sunan route'a gider. `Ödemeden vazgeç`: mağazaya
  döner, tutar ve taksit korunur.
- Bankanın 3D sayfasında bizim header'ımız ve rulomuz görünmez. Bu beklenen durumdur.
- Bankadan dönüşte sunucu `payments.complete_3ds_payment` çağırır ve sonuç sayfasını
  render eder. Bu kayıt, sonuç sayfası açılınca rulonun en üstünde "yeni" olarak işaretlenir
  (bkz. 6.5).

### 4.3 Sonuç (`/odeme/sonuc`)

Sayfa yüklenince odak h1'e taşınır (`tabindex="-1"`).

**Başarılı**
```
| Ödeme alındı (h1)                                    [Başarılı] |
| Bakır cezve, 2 fincanlık siparişiniz onaylandı.                 |
|                                                                 |
| 1.287,00 TL  (fs-6)                                             |
|                                                                 |
| Taksit       3 taksit, aylık 429,00 TL                          |
| Ödeme no     184522                                            |
| Sipariş no   DEMO-20261110-0007                                 |
| Durum        Başarılı                                           |
|                                                                 |
| [ Siparişleri görüntüle ]   [ Yeni ödeme yap ]                  |
```

**Başarısız**
```
| Ödeme alınamadı (h1)                                [Başarısız] |
| Kartınızdan para çekilmedi.                                     |
|                                                                 |
| +-- ret-zemin, kenar 1px ret ---------------------------------+ |
| | Bankanın yanıtı                                             | |
| | "Kart limiti yetersiz."                     (fs-4, mürekkep) | |
| | Hata kodu 51                                                | |
| +-------------------------------------------------------------+ |
| Başka bir kartla ya da daha düşük tutarla tekrar deneyin.       |
|                                                                 |
| Tutar 1.287,00 TL   Ödeme no 184523   Sipariş no DEMO-...-0008  |
|                                                                 |
| [ Ödemeyi tekrar dene ]   [ Siparişleri görüntüle ]             |
```
- Banka mesajı değiştirilmeden, tırnak içinde gösterilir. Mesaj yoksa: `Banka bir açıklama
  göndermedi.`
- Hata kutusu: zemin `--color-ret-zemin`, kenar 1px `--color-ret`, `--radius-yok`,
  padding `--space-4`, `role="alert"` değil (sayfa zaten bu içerik için açıldı).
- Ne yapmalı satırı (koda göre seçilir, eşleşme yoksa varsayılan):
  - Bakiye/limit: `Başka bir kartla ya da daha düşük tutarla tekrar deneyin.`
  - 3D doğrulama başarısız: `Bankanın gönderdiği SMS kodunu doğru girdiğinizden emin olup
    tekrar deneyin.`
  - Bağlantı/zaman aşımı (SDK `ConnectionException`): `MagicPay'e ulaşılamadı. Bir dakika
    sonra tekrar deneyin; kartınızdan para çekilmedi.`
  - Varsayılan: `Kart bilgilerini kontrol edip tekrar deneyin.`
- `Ödemeyi tekrar dene`: mağazaya döner. Tutar ve taksit seçimi korunur, kart alanları
  yeniden test kartıyla dolar. (İstekteki "Tekrar dene" metni, butonun ne yaptığını söylemesi
  için `Ödemeyi tekrar dene` olarak netleştirildi.)
- Ödeme no veya sipariş no yoksa (örn. init aşamasında hata) o terim hiç yazılmaz.

### 4.4 Siparişler (`/siparisler`)

Bu demo oturumunda yapılan ödemeler, en yenisi üstte.

```
| Siparişler (h1)                                                               |
| Bu oturumda yapılan ödemeler. Durumu MagicPay'den sorgulayabilir ya da        |
| ödemeyi iade edebilirsiniz.                                                   |
|                                                                               |
| Zaman  Ödeme no / Sipariş no      Tutar        Durum          İşlemler        |
| ----------------------------------------------------------------------------- |
| 14:32  184522                     1.287,00 TL  [Başarılı]     [Durumu sorgula] [İade et] |
|        DEMO-20261110-0007                      Son sorgu 14:35: durum aynı.    |
| ----------------------------------------------------------------------------- |
|   1.287,00 TL'nin tamamı karta iade edilecek. Bu işlem geri alınamaz.          |
|   [ İadeyi onayla ]  [ Vazgeç ]                     (satır içi onay, ret-zemin yok) |
| ----------------------------------------------------------------------------- |
| 14:20  184519                     250,00 TL    [İade edildi]  [Durumu sorgula] |
|        DEMO-20261110-0004                      İade no 55321                   |
```

- Gerçek `<table>`, `--radius-yok`, yalnızca yatay `--border-cizgi` satır çizgileri, dikey
  çizgi yok. Başlık `--fs-1`, `--fw-vurgu`, soluk. Hücre padding `--space-3 --space-3`.
- `Ödeme no / Sipariş no` hücresi iki satırdır: ödeme no `--fw-vurgu`, sipariş no altında
  soluk `--fs-2`. Arayüz fontu, tabular. Mono kullanılmaz.
- Tutar sağa hizalı. Zaman `SS:DD` (aynı gün), gün farklıysa `10.11 14:32`.
- İşlemler: küçük ikincil butonlar (`--kontrol-h-kucuk`) yan yana, araları `--space-2`.
  - `Durumu sorgula` → `payments.retrieve_payment(id)`. Basılınca `Sorgulanıyor…`. Sonuçta
    durum etiketi güncellenir ve altına `--fs-1` soluk not düşülür:
    `Son sorgu 14:35: durum aynı.` ya da `Son sorgu 14:35: durum "İade edildi" olarak
    güncellendi.`
  - `İade et` → satırın altında tam genişlikte bir onay satırı açılır (modal yok, rulo
    görünür kalsın diye). Metin: `{tutar}'nin tamamı karta iade edilecek. Bu işlem geri
    alınamaz.` Butonlar: `İadeyi onayla` (tehlike butonu) ve `Vazgeç` (ikincil). Açılınca
    odak `Vazgeç`'e gelir, `Esc` onayı kapatır ve odağı `İade et`'e geri verir.
  - `İadeyi onayla` → `payments.refund_payment({paymentId})`. Basılınca `İade ediliyor…`.
    Başarılıysa etiket `İade edildi` olur, `İade et` butonu kaldırılır, altına
    `İade no 55321` yazılır. Hata olursa onay satırında ret renginde:
    `İade yapılamadı: "{banka mesajı}" (kod {kod}). Durumu sorgulayıp tekrar deneyin.`
- `İade et` yalnızca `Başarılı` durumda görünür. `İade edildi`, `İptal edildi`,
  `Başarısız`, `3D bekleniyor` satırlarında yalnızca `Durumu sorgula` vardır.
- Boş durum (tablo yerine): `Bu oturumda henüz ödeme yok. İlk ödemeyi mağaza sayfasından
  yapın.` ve birincil buton `Mağazaya git`.

**Durum etiketleri** (her yerde aynı: sonuç sayfası, sipariş tablosu). `--fs-2`,
`--fw-vurgu`, cümle düzeni, padding `2px var(--space-2)`, `--radius-etiket`, 1px kenar metin
renginde. İkon yok, anlam metinle verilir.

| API değeri (`paymentStatus` vb.) | Etiket | Metin | Zemin |
|---|---|---|---|
| `SUCCESS` | `Başarılı` | onay | onay-zemin |
| `FAILURE` | `Başarısız` | ret | ret-zemin |
| `INIT_THREEDS`, `CALLBACK_THREEDS` | `3D bekleniyor` | bekleme | bekleme-zemin |
| iade tamamlandı | `İade edildi` | mürekkep | kâğıt |
| iptal | `İptal edildi` | mürekkep | kâğıt |
| tanınmayan değer | ham değer, örn. `PARTIAL_REFUND` | soluk | kâğıt |

### 4.5 Bağlantı kontrolü (`/baglanti`)

Yalnızca okuma yapan çağrılar. Her kontrol önce V2, sonra V1 imzayla, **sırayla** çalışır.
Böylece rulo videoda tek tek dolar.

```
| Bağlantı kontrolü (h1)                                                         |
| API anahtarınızın ve imzanızın test ortamında çalıştığını, yalnızca okuma yapan |
| çağrılarla doğrular. Para hareketi olmaz.                                       |
|                                                                                 |
| [ Kontrolleri çalıştır ]                                                        |
|                                                                                 |
| Kontrol               SDK metodu                               V2 imza        V1 imza        |
| ------------------------------------------------------------------------------- |
| Taksit seçenekleri    installments.list_checkout_installments   Geçti, 182 ms  Geçti, 175 ms  |
| BIN sorgusu           installments.retrieve_bin                 Geçti, 96 ms   Çalışıyor…     |
| Kart bankası sorgusu  installments.check_bin                    Bekliyor       Bekliyor       |
|  (imza gerekmez)                                                                |
| POS kimlikleri        pos.list_pos_ids                          Bekliyor       Bekliyor       |
| Ödeme linki taksitleri magic_links.list_available_installments  Bekliyor       Bekliyor       |
| API anahtarları       api_keys.list_api_credentials             Bekliyor       Bekliyor       |
| Üyeler                api_members.list_members                  Bekliyor       Bekliyor       |
| Eklenti bankaları     plugin.list_banks                         Bekliyor       Yalnızca V2    |
| Eklenti POS listesi   plugin.list_poses                         Bekliyor       Yalnızca V2    |
| ------------------------------------------------------------------------------- |
| 16 kontrol çalıştı: 16 geçti, 0 başarısız.                                       |
```

Kontrol listesi (9 satır, 16 çağrı: 7 satır V2 + V1, eklenti satırları yalnızca V2):
`installments.list_checkout_installments`, `installments.retrieve_bin`, `installments.check_bin`
(imza gerekmeyen uç; rulo `İmzasız` yazar), `pos.list_pos_ids`,
`magic_links.list_available_installments`, `api_keys.list_api_credentials`,
`api_members.list_members`, `plugin.list_banks` (yalnızca V2), `plugin.list_poses` (yalnızca V2).
`SDK metodu` sütununda metot adı yalnızca noktadan sonra kırılır, kelime ortasında kırılmaz.

- Tablo yapısı sipariş tablosuyla aynı. `SDK metodu` sütunu mono `--fs-2` (kod tanımlayıcısı).
- Sonuç hücreleri (`--fs-2`):
  - `Bekliyor`: soluk.
  - `Çalışıyor…`: mürekkep, `aria-busy="true"`.
  - `Geçti, 182 ms`: `Geçti` onay renginde `--fw-vurgu`, süre soluk.
  - `Başarısız`: ret renginde `--fw-vurgu`. Altında `--fs-1`: `HTTP 401, kod 1001: İmza
    doğrulanamadı.` Hücre zemini `--color-ret-zemin`.
  - `Yalnızca V2`: soluk. `title`: `Bu uç yalnızca V2 imzayla çalışır; V1 denenmez.`
- Buton çalışırken: devre dışı, metin `Kontroller çalışıyor…`. Bitince: `Kontrolleri
  yeniden çalıştır`.
- Özet satırı (`--fs-3`, `aria-live="polite"`):
  - Hepsi geçtiyse: `16 kontrol çalıştı: 16 geçti, 0 başarısız. Entegrasyon test ortamında
    hazır.`
  - Başarısız varsa: `16 kontrol çalıştı: 14 geçti, 2 başarısız. Başarısız satırlardaki
    hata kodunu inceleyin; 401 ve 403 çoğunlukla API anahtarının yetkisinin eksik olduğunu
    gösterir.`
  - Rakamdan sonra ek gelmeyecek biçimde yazıldı (`10'u` / `12'si` sorunu yok).
- İlk açılış (henüz çalışmadı): tablo `Bekliyor` hücreleriyle görünür, özet satırı yerine:
  `Kontrolleri çalıştırınca her çağrı sağdaki SDK kaydında da görünür.`
  Mobilde "sağdaki" yerine "aşağıdaki" yazılır.
- Mobil: tablo, kontrol başına bir blok olur (ad, metot, `V2 imza: …`, `V1 imza: …`
  satırları). Bloklar `--border-cizgi` ile ayrılır, kutu ve gölge kullanılmaz.

---

## 5. Ortak bileşenler

### 5.1 Header

- Yükseklik `--header-h`, zemin kâğıt, alt kenar `--border-cizgi`. Grid'i sayfanınkiyle
  aynıdır, böylece dikiş header'dan aşağı kesintisiz iner.
- Sol parça: mağaza adı (`{{ merchant_name }}`, örn. `Kalaycı Bakır`, `--fs-3`,
  `--fw-guclu`), ardından `--space-6` aralıkla nav: `Mağaza`, `Siparişler`,
  `Bağlantı kontrolü`. Linkler `--fs-2`, mürekkep. Aktif sayfa `--fw-vurgu`, 2px mürekkep alt
  çizgi, `aria-current="page"`. Hover: alt çizgi `--color-kenar`. Dokunma hedefi min
  44px yükseklik.
- Sağ parça (rulonun üstü, padding `--space-5`): test ortamı etiketi. Metin
  `Test ortamı (trdev.magicpay.ai)`, `--fs-2`, `--fw-vurgu`, `--color-bekleme`, zemin
  `--color-bekleme-zemin`, kenar 1px `--color-bekleme`, `--radius-etiket`. Bu etiket bilgi
  taşır: gerçek para hareketi olmadığını söyler.

### 5.2 Butonlar

| Tür | Kullanım | Görünüm |
|---|---|---|
| Birincil | Ödeme, `Banka sayfasına geç`, `Siparişleri görüntüle`, `Mağazaya git`, `Kontrolleri çalıştır` | zemin mürekkep, metin kâğıt, yükseklik `--kontrol-h`, padding `0 var(--space-5)`, `--fs-3` `--fw-vurgu`, `--radius-kontrol`. Hover: zemin `--color-murekkep-2` |
| İkincil | `Yeni ödeme yap`, `Vazgeç`, `Tutarı uygula`, tablo içi işlemler | zemin kâğıt, 1px mürekkep kenar, metin mürekkep. Hover: zemin `--color-rulo` |
| Tehlike | yalnızca `İadeyi onayla` | zemin ret, metin kâğıt, ölçüler birincille aynı. Hover: zemin aynı kalır, metne alt çizgi gelir |
| Metin | `Ödemeden vazgeç` | alt çizgili mürekkep link, min 44px dokunma alanı |

- Devre dışı: zemin `--color-cizgi`, metin `--color-soluk`, `cursor: not-allowed`. Opaklık
  ile soldurulmaz.
- Yükleniyor: buton devre dışı ve metni eylemin sürdüğünü söyler (`Ödeme başlatılıyor…`,
  `Sorgulanıyor…`, `İade ediliyor…`, `Kontroller çalışıyor…`). Spinner yok.
- Buton metinlerinin sonuna ok veya ikon eklenmez. Hover'da büyüme ve gölge yoktur, yalnızca
  renk değişir (`--sure-tepki`).

### 5.3 İkonlar

Yalnızca iki satır içi SVG kullanılır (16px, stroke 1.75, `currentColor`):
**chevron** (kayıt satırını aç/kapa) ve **kopyala** (JSON kopyalama). Emoji yok, başka ikon yok.

---

## 6. SDK kaydı (sunucu fiş rulosu)

Kayıtlar sunucu oturumunda tutulur ve sayfa değişse de kalır. Her sayfada aynı panel render
edilir. Yeni kayıtlar JS ile (fetch sonrası ya da kısa aralıklı yoklamayla) eklenir.

### 6.1 Yazıcı ağzı (panel başlığı)

```
+--------------------------------------------------+
| SDK çağrıları            7 çağrı  [Günlüğü temizle] |  zemin mürekkep
| Sunucunuzdaki magicpay SDK'sının MagicPay'e        |
| yaptığı istekler. En yenisi üstte.                 |
+==================================================+  --border-agiz (3px)
```
- Zemin `--color-murekkep`, padding `--space-4 --space-5`. Başlık `SDK çağrıları`
  (`--fs-3`, `--fw-vurgu`, kâğıt rengi). Sayaç `7 çağrı` (`--fs-1`, `--color-agiz-metin`,
  tabular). Açıklama `--fs-1`, `--color-agiz-metin`.
- `Günlüğü temizle`: ikincil buton tersine çevrilmiş hali. Şeffaf zemin, 1px kâğıt rengi
  kenar, kâğıt rengi metin, yükseklik 32px, `--fs-1`. Onay istemez, kaydı hemen hem
  istemcide hem sunucu oturumunda siler. Ardından boş durum metni görünür ve odak
  rulonun başlığına (`tabindex="-1"`) taşınır.
- Alt dudak `--border-agiz`. Kayıt listesi bu dudağın altından başlar ve
  `overflow: hidden` olan bir kapsayıcı içindedir (6.5'teki besleme hareketi için).

### 6.2 Kayıt satırı (kapalı)

Rulo zemini üzerinde, kutusuz. Her satırın üstünde `--border-yirtma`. Padding
`--space-3 --space-5`. Satırın tamamı bir `<button aria-expanded="false">`dır.

```
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
 payments.init_3ds_payment                    İmza V2   HTTP 200   412 ms  [v]
 POST /payment/v1/card-payments/3ds-init
 #7  14:32:07  Tetikleyen: Ödeme butonu
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
```

| Satır | İçerik | Font |
|---|---|---|
| 1, sol | SDK metot adı, örn. `payments.init_3ds_payment` | mono, `--fs-3`, `--fw-vurgu`, mürekkep |
| 1, sağ | üç ayrı alan: imza (`İmza V2`, `İmza V1` ya da `İmzasız`), `HTTP 200`, `412 ms`. Aralarında `--space-4` boşluk var, ayraç karakteri yok | arayüz, `--fs-2`, tabular. HTTP 2xx mürekkep, ≥400 ret + `--fw-guclu` |
| 2 | HTTP metodu + path (`POST` `--fw-vurgu`), query varsa path'ten sonra `?amount=1250&currency=TRY` | mono, `--fs-2`, soluk |
| 3 | Sıra no (`#7`, oturumdaki gerçek çağrı sırası), saat `SS:DD:ss`, `Tetikleyen: …` | arayüz, `--fs-1`, soluk |
| 4 (yalnız hata) | bkz. 6.4 | arayüz, `--fs-2`, ret |
| sağ uç | chevron, açıkken 180° döner | 16px |

- "İmza" etiketi bilerek açık yazılır, böylece işletme tarafındaki izleyici "V2"yi
  anlamlandırabilir. `installments.check_bin` gibi kimlik doğrulamasız uçlarda `İmzasız`
  yazılır.
- Satır 1 dar panelde (400px) kırılır: sağ küme metot adının altına iner.
- Hover: zemin `--color-secim` (rulo üstünde hafif mavi). Büyüme yok.
- Ekran okuyucu metni (görünmez): `Ayrıntıları göster` / `Ayrıntıları gizle`.

**Tetikleyen metinleri** (uygulama her çağrıya bunu verir, ekran ile kaydı birbirine bağlayan
alan budur):

| SDK metodu | Tetikleyen |
|---|---|
| `installments.list_checkout_installments` | `Sayfa açılışı` / `Tutarı uygula` / `Bağlantı kontrolü` |
| `installments.retrieve_bin` | `Kart numarasının ilk 6 hanesi` / `Bağlantı kontrolü` |
| `payments.init_3ds_payment` | `Ödeme butonu` |
| `payments.complete_3ds_payment` | `Bankadan dönüş` |
| `payments.retrieve_payment` | `Durumu sorgula` |
| `payments.refund_payment` | `İadeyi onayla` |
| `installments.check_bin`, `pos.list_pos_ids`, `magic_links.list_available_installments`, `api_keys.list_api_credentials`, `api_members.list_members`, `plugin.list_banks`, `plugin.list_poses` | `Bağlantı kontrolü` |

### 6.3 Kayıt satırı (açık)

```
 payments.init_3ds_payment                    İmza V2   HTTP 200   412 ms  [^]
 POST /payment/v1/card-payments/3ds-init
 #7  14:32:07  Tetikleyen: Ödeme butonu

 İstek                                                      [İsteği kopyala]
 +--------------------------------------------------------------------------+
 | {                                                                        |
 |   "amount": 1287.00,                                                     |
 |   "installment": 3,                                                      |
 |   "card": {                                                              |
 |     "cardNumber": "415565******0012",                                    |
 |     "expireMonth": "**", "expireYear": "**", "cvc": "***", ...           |
 +--------------------------------------------------------------------------+
 Yanıt                                                      [Yanıtı kopyala]
 +--------------------------------------------------------------------------+
 | { "paymentId": 184522, "htmlContent": "<!DOCTYPE html>… (4.812 karakter  |
 |   daha, kısaltıldı)" }                                                   |
 +--------------------------------------------------------------------------+
 Kart numarası, son kullanma tarihi, CVC ve gizli anahtarlar gizlendi.
```

- `İstek` / `Yanıt` başlıkları `--fs-2`, `--fw-vurgu`. GET isteklerinde istek bloğu yerine
  query parametreleri JSON olarak gösterilir. Gövde yoksa `Gövde yok.` yazılır.
- JSON bloğu: zemin `--color-kagit`, kenar `--border-cizgi`, `--radius-yok`, padding
  `--space-3`, mono `--fs-1`, `--lh-govde`, 2 boşluk girinti, `white-space: pre-wrap`,
  `overflow-wrap: anywhere`, `max-height: 360px` ve kendi içinde kaydırma. Renkli sözdizimi
  vurgusu yok. Anahtarlar `--fw-vurgu`, değerler normal.
- Kopyala butonları metin butonudur (kopyala ikonu + metin, 32px). Tıklanınca metin 2 sn
  `Kopyalandı` olur. Kopyalanan metin maskeli halidir.
- Hata satırında yanıt başlığı `Yanıt (hata)` olur.
- Birden fazla satır aynı anda açık olabilir.

**Maskeleme kuralları** (sunucuda, kayda yazılmadan önce uygulanır, istemciye maskesiz veri
gitmez):
- Kart numarası: ilk 6 + `*` + son 4 → `415565******0012`.
- `cvc`, `cvv`, `expireMonth`, `expireYear`: tüm karakterler `*`.
- Anahtar adı `secret`, `password`, `token`, `signature`, `storeKey`, `apiKey`,
  `authorization` içeren her alan (büyük/küçük harf duyarsız): `"****"`.
- Maskeli değerler `--color-soluk` ile yazılır, `title="Gizlendi"`.
- 300 karakterden uzun string (3D HTML'i gibi): ilk 60 karakter + `… ({n} karakter daha,
  kısaltıldı)`. Sayı Türkçe binlik ayraçla yazılır.
- Blok altındaki not her açık satırda görünür: `Kart numarası, son kullanma tarihi, CVC ve
  gizli anahtarlar gizlendi.`

### 6.4 Hata satırı ile başarılı satırın farkı

Hata satırı şu durumlardan biridir: HTTP ≥ 400, SDK'nın bağlantı/zaman aşımı hatası,
ya da 2xx yanıtta `errorCode` dolu veya ödeme durumu `FAILURE` (banka reddi).
Farkı üç işaret birlikte verir, yalnızca renge güvenilmez:

1. Satırın tamamının zemini `--color-ret-zemin` (yırtma çizgisi aynı kalır).
2. HTTP durumu ret renginde ve `--fw-guclu` (banka reddinde HTTP 200 mürekkep kalır).
3. Ek bir 4. satır ret renginde, kelimeyle başlar:
   - HTTP hatası: `Hata {kod}: {mesaj}` → `Hata 1001: İmza doğrulanamadı.`
   - Banka reddi: `Banka reddetti: "{banka mesajı}" (kod {kod})`
   - Bağlantı: HTTP alanında `Yanıt yok`, 4. satırda `MagicPay'e ulaşılamadı (zaman aşımı,
     30 sn).`

Başarılı satırın ek satırı ve zemin rengi yoktur.

### 6.5 Yeni satırın planlı anı

Bu arayüzdeki tek planlı hareket budur ve doğrudan bir olaya (yeni SDK çağrısına) bağlıdır.

- **Besleme:** yeni satır listenin en üstüne eklenir ve
  `transform: translateY(-100%)` → `none`, `--sure-besleme`, `--egri-besleme` ile hareket
  eder. Liste kapsayıcısı `overflow: hidden` olduğu için satır yazıcı ağzının altından
  çıkıyor gibi görünür. Altındaki satırlar aynı sürede aşağı kayar (kapsayıcı yüksekliği
  değil, satırların `transform`'u animasyonlanır).
- **Fosfor işareti:** yeni satırın zemini `--color-fosfor` olur, 600 ms öyle kalır, sonra
  1200 ms içinde satırın normal zeminine (rulo ya da ret-zemin) döner.
- **Yığılma:** 1 saniye içinde 3'ten fazla satır gelirse (bağlantı kontrolü) besleme
  hareketi atlanır, yalnızca fosfor işareti uygulanır.
- **Hangi satır "yeni":** sayfa açıkken gelenler, ve sayfa yüklendiğinde sunucunun bu
  istekte ürettiği kayıtlar (örn. sonuç sayfasındaki `complete_3ds_payment`). Bunun için son
  görülen sıra no `sessionStorage`'da tutulur, ondan büyük olanlar işaretlenir. Diğer sayfa
  yüklemelerinde eski satırlar işaretlenmez.
- **Kaydırma:** kullanıcı ruloyu aşağı kaydırmışsa (scrollTop > 0) yeni satır listeyi
  zıplatmaz. Rulonun üstünde yapışkan bir metin butonu belirir: `1 yeni çağrı, en üste git`
  (sayı güncellenir). Tıklanınca en üste kaydırır ve buton kaybolur.
- **Ekran okuyucu:** ayrı, görünmez bir `aria-live="polite"` bölgesi her yeni kayıtta kısa
  metin okur: `Yeni SDK çağrısı: payments.init_3ds_payment, HTTP 200.` Hata satırında:
  `Hatalı SDK çağrısı: payments.refund_payment, HTTP 400.`

### 6.6 Boş durumlar

- Hiç kayıt yok (ilk açılış): `Henüz SDK çağrısı yok. Kart numarasını değiştirin ya da ödeme
  yapın; sunucunun yaptığı her çağrı burada görünür.`
- Temizlendikten sonra: `Günlük temizlendi. Bir sonraki SDK çağrısı burada görünecek.`
- Metin `--fs-2`, soluk, padding `--space-5`.

### 6.7 Mobil (375) davranışı

- Rulo içeriğin altında, varsayılan **kapalı**. Yazıcı ağzı aynı zamanda açma düğmesidir:
  tam genişlik, min 48px, `aria-expanded`, `aria-controls`.
  - Kapalıyken: `SDK çağrıları (7)` + sağda `Göster`. İkinci satırda (varsa) son çağrı:
    `Son çağrı: payments.init_3ds_payment, HTTP 200` (hatada `HTTP 400, hata`).
  - Açıkken: `SDK çağrıları (7)` + `Gizle`. Açıklama metni ve `Günlüğü temizle` ağzın
    içinde görünür.
- Açık/kapalı tercihi `sessionStorage`'da sayfalar arasında korunur.
- Açıkken rulo sayfayla birlikte akar, kendi yüksekliği sınırlı değildir. JSON blokları
  `max-height: 360px` kuralını korur.
- Satır 1'in sağ kümesi metot adının altına iner. Path ve JSON kırılır, yatay kaydırma yok.
- Kapalıyken besleme hareketi yoktur. Yalnızca "Son çağrı" satırı güncellenir.

---

## 7. Odak, hareket ve azaltılmış hareket

**Odak**
- Tüm etkileşimli öğelerde `:focus-visible { outline: var(--odak-halkasi); outline-offset: 2px; }`.
  `outline: none` hiçbir yerde kullanılmaz. Halka mürekkep zeminli butonda da beyaz boşluk
  üstüne düştüğü için görünür. Yazıcı ağzındaki öğelerde offset `-4px` ve renk kâğıt
  (`outline-color: var(--color-kagit)`).
- Taksit radio'larında odak halkası satırın tamamına çizilir
  (`tr:has(input:focus-visible)`).
- Sekme sırası: atlama linki → header → içerik → rulo (DOM sırası; mobilde de aynı).
- Sonuç sayfasında odak h1'e, iade onayında `Vazgeç`'e, günlük temizlenince rulo
  başlığına taşınır.
- Dokunma hedefleri min 44×44px (rulo içindeki metin butonları min 32px yükseklik, tam
  satır genişliği tıklanabilir).

**Hareket**
- İzin verilenler yalnızca şunlardır: 6.5'teki besleme + fosfor (planlı an), chevron dönüşü
  (`--sure-tepki`), hover'da renk geçişi (`--sure-tepki`).
- Sayfa girişi, bölüm girişi, kart büyümesi, spinner, iskelet yükleyici ve süs animasyonu
  yoktur.

**Azaltılmış hareket** (`@media (prefers-reduced-motion: reduce)`)
- Besleme hareketi kapalıdır, satır doğrudan yerinde görünür.
- Fosfor işareti sönmeden uygulanır: zemin 2 sn `--color-fosfor`, sonra geçişsiz kalkar.
- Chevron dönüşü ve hover geçişleri `transition: none`.
- `scroll-behavior: auto` (`en üste git` anında kaydırır).

---

## 8. Metin sözlüğü (tek kaynak)

Aynı eylem akış boyunca aynı adı taşır.

| Yer | Metin |
|---|---|
| Nav | `Mağaza`, `Siparişler`, `Bağlantı kontrolü` |
| Test etiketi | `Test ortamı (trdev.magicpay.ai)` (mobil: `Test ortamı`) |
| Atlama linki | `SDK çağrılarına atla` |
| Sayfa başlıkları (`<title>`) | `Ödeme - {mağaza}`, `Banka doğrulaması - {mağaza}`, `Ödeme alındı - {mağaza}`, `Ödeme alınamadı - {mağaza}`, `Siparişler - {mağaza}`, `Bağlantı kontrolü - {mağaza}` |
| Ürün | `Bakır cezve, 2 fincanlık` / `Gaziantep'te elde dövülmüş, içi kalaylı bakır cezve. Ahşap saplı, 250 ml.` |
| Demo ayarı | `Demo ayarı: ödeme tutarı`, `Tutarı uygula`, `Taksit tablosu yeni tutara göre yeniden hesaplanır.` |
| Form | `Kart bilgileri`, `Kart numarası`, `Kart üzerindeki isim`, `Son kullanma tarihi`, `Güvenlik kodu`, `Kart alanları EsnekPOS test kartıyla dolduruldu. Gerçek kart bilgisi girmeyin.` |
| Taksit | `Taksit seçimi`, `Taksit`, `Aylık`, `Toplam`, `Tek çekim`, `{n} taksit` |
| Ödeme | `Ödenecek tutar`, `{tutar} öde`, `{n} taksitle {tutar} öde`, `Ödeme başlatılıyor…`, `Ödemeyi bankanızın 3D Secure sayfasında onaylayacaksınız.` |
| Yönlendirme | `Banka doğrulaması`, `Banka sayfasına geç`, `Ödemeden vazgeç`, `Banka sayfası bankanın kendi tasarımıdır; bu mağazaya ait değil.` |
| Sonuç | `Ödeme alındı`, `{ürün} siparişiniz onaylandı.`, `Ödeme alınamadı`, `Kartınızdan para çekilmedi.`, `Bankanın yanıtı`, `Hata kodu {kod}`, `Ödemeyi tekrar dene`, `Siparişleri görüntüle`, `Yeni ödeme yap` |
| Terimler | `Tutar`, `Taksit`, `Kart`, `Ödeme no`, `Sipariş no`, `İade no`, `Durum`, `Zaman` |
| Siparişler | `Durumu sorgula`, `Sorgulanıyor…`, `İade et`, `İadeyi onayla`, `İade ediliyor…`, `Vazgeç`, `Mağazaya git` |
| Bağlantı | `Kontrolleri çalıştır`, `Kontroller çalışıyor…`, `Kontrolleri yeniden çalıştır`, `Bekliyor`, `Çalışıyor…`, `Geçti`, `Başarısız`, `Yalnızca V2` |
| Rulo | `SDK çağrıları`, `{n} çağrı`, `Günlüğü temizle`, `İstek`, `Yanıt`, `Yanıt (hata)`, `Gövde yok.`, `İsteği kopyala`, `Yanıtı kopyala`, `Kopyalandı`, `Göster`, `Gizle`, `{n} yeni çağrı, en üste git`, `İmza V2`, `İmza V1`, `İmzasız`, `Tetikleyen:` |

**Genel hata metinleri**
- SDK ayarı eksik (her sayfanın üstünde, ret-zemin şerit): `MagicPay API anahtarı tanımlı
  değil. .env dosyasına MAGICPAY_API_KEY ve MAGICPAY_SECRET_KEY ekleyip uygulamayı yeniden
  başlatın.` (Değişken adları SDK'nın gerçek adlarıyla eşleştirilmeli.)
- Beklenmeyen sunucu hatası: `İşlem tamamlanamadı. Sağdaki SDK kaydında son satırı açıp
  hatayı inceleyin, ardından tekrar deneyin.`

**Biçim kuralları**
- Para: `1.287,00 TL` (binlik nokta, ondalık virgül, boşluk + `TL`). `₺` kullanılmaz.
- Süre: `412 ms`. Saat: `14:32:07` (rulo), `14:32` (tablo).
- Türkçe büyük harf dönüşümü gerekirse `toLocaleUpperCase('tr-TR')`. Arayüzde büyük harf
  dönüşümü zaten kullanılmaz.
- Rakamdan sonra ek gerektiren cümlelerden kaçınılır ya da ek doğru üretilir
  (`{tutar}'nin` için tutar her zaman `TL` ile bittiğinden `'nin` sabittir).

---

## 9. Yapılmayacaklar (bu proje için)

- Sağ panelde koyu "terminal" teması, renkli sözdizimi vurgusu, neon yeşil.
- Kayıt satırlarını ayrı yuvarlatılmış kutulara bölmek, herhangi bir `box-shadow`.
- Durum, etiket, tablo başlığı için büyük harf. Başlık üstü küçük etiket.
- Ödeme no, sipariş no, tutar, süre ve saat için mono font.
- Bağlantı kontrolü satırlarını 01/02 diye numaralamak. Rulodaki `#7` gerçek çağrı
  sırasıdır ve yalnızca orada kullanılır.
- Modal pencere. Onaylar satır içinde yapılır, çünkü rulo görünür kalmalı.
- Buton sonunda ok, emoji, ara noktalı meta satırı.
