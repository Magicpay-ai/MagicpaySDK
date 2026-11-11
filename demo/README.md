# MagicPay SDK demo mağazası

Python SDK'sını (`../python/magicpay`) kullanan yerel bir demo. Solda mağaza, sağda sunucudaki
SDK'nın MagicPay'e yaptığı her çağrının maskeli kaydı (fiş rulosu). Tasarım: `DESIGN.md`.

SDK kurulmaz; uygulama `../python` klasörünü `sys.path`'e ekler.

## Kurulum

```powershell
cd demo
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Ortam değişkenleri

| Değişken | Zorunlu | Varsayılan |
|---|---|---|
| `MAGICPAY_API_KEY` | evet (ortamın anahtarı) | |
| `MAGICPAY_SECRET_KEY` | evet (ortamın anahtarı) | |
| `DEMO_AMOUNT` | hayır | test ortamında `1250.00`, canlıda `1.00` |
| `MAGICPAY_BASE_URL` | hayır | `https://trdev.magicpay.ai` (SDK'nın `SANDBOX_URL`'i) |
| `MAGICPAY_MERCHANT_NAME` | hayır | `Demo Mağaza` (header'daki mağaza adı) |
| `DEMO_PUBLIC_URL` | hayır | `http://127.0.0.1:8000` (bankanın dönüş adresi bundan kurulur) |

Anahtarlar yoksa uygulama çökmez; her sayfanın üstünde kurulum uyarısı görünür.

## Çalıştırma

Anahtarları dosyaya yazmayın ve komut satırına düz metin olarak yazmayın: komut geçmişinde kalır,
kayıtta görünür. **Terminali kaydetmeyin.** Uygulamayı kaydedilmeyen ayrı bir pencerede başlatın
ve anahtarları gizli girişle okuyun:

```powershell
$k = Read-Host "MAGICPAY_API_KEY" -AsSecureString
$s = Read-Host "MAGICPAY_SECRET_KEY" -AsSecureString
$env:MAGICPAY_API_KEY = [Net.NetworkCredential]::new("", $k).Password
$env:MAGICPAY_SECRET_KEY = [Net.NetworkCredential]::new("", $s).Password
Remove-Variable k, s
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Tarayıcıda `http://127.0.0.1:8000` adresini açın.

Kısa yol: `start.ps1` aynı adımları yapar (anahtarları gizli okur, 8010 portunda başlatır,
tarayıcıyı açar).

```powershell
.\start.ps1              # canlı ortam: https://tr.magicpay.ai, canlı anahtar
.\start.ps1 -Ortam test  # test ortamı: https://trdev.magicpay.ai, test anahtarı
```

Canlı ortamda gerçek karttan gerçek tutar çekilir: kart alanları boş gelir, varsayılan tutar
1,00 TL'dir (`DEMO_AMOUNT` ile değişir). Ödemeyi aynı gün **Siparişler** sayfasından iade edin.

- Uygulamayı **asla** `--host 0.0.0.0` ile ya da bir tünelle (ngrok, Cloudflare Tunnel vb.)
  dışarı açmayın: sayfalar API anahtarınızla MagicPay'e çağrı yapar. `DEMO_PUBLIC_URL`
  127.0.0.1 ya da localhost değilse uygulama başlamaz.
- `--no-access-log` terminale istek adresi basılmasını önler.

8000 doluysa (örneğin Docker Desktop kullanıyorsa) başka bir port seçin ve bankanın dönüş
adresi doğru kurulsun diye `DEMO_PUBLIC_URL`'i de aynı porta ayarlayın:

```powershell
$env:DEMO_PUBLIC_URL = "http://127.0.0.1:8010"
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8010 --no-access-log
```

Tarayıcıda `localhost` yerine `DEMO_PUBLIC_URL`'deki adresi (127.0.0.1) kullanın.

## Nasıl çalışır

- Kart formu EsnekPOS'un herkese açık başarılı test kartıyla dolu gelir. Gerçek kart girmeyin.
- `Öde` → sunucu `payments.init_3ds_payment` çağırır → ara ekran → `Banka sayfasına geç`
  bankanın 3D formunu olduğu gibi açar.
- EsnekPOS test sayfasında onay şifresi dolu gelir: `ONAYLA`'ya basın. `VAZGEÇ` başarısız ödeme verir.
- Banka tarayıcıyı `DEMO_PUBLIC_URL/odeme/donus/...` adresine döndürür. Bankanın `?status=`
  parametresi yalnızca ipucudur; sunucu `payments.complete_3ds_payment` çağırır ve sonucu ona
  göre gösterir. Banka henüz karar vermediyse sonuç sayfası "Durumu sorgula" düğmesiyle bekler.
- `callbackUrl` olarak `https://example.com/callback` gönderilir: MagicPay sunucusu bu
  bilgisayara ulaşamaz, bu yüzden demo sonucu sunucu tarafında `3ds-complete` ile doğrular.
- Siparişler yalnızca bellekte tutulur, uygulama kapanınca silinir. Kart bilgisi hiçbir yere
  yazılmaz. Rulodaki kayıtlar sunucuda maskelenir (kart numarası ilk 6 + son 4, CVC ve son
  kullanma tarihi, `x-api-key`, imza ve gizli alanlar tamamen; bankanın 3D formu ve dönüş adresindeki
  token gizlenir; API anahtarı ve üye listelerinde yalnızca izin verilen alanlar görünür).

## Kayıt kontrol listesi

1. Kaydedilmeyen bir pencerede anahtarları gizli girişle tanımlayıp uygulamayı başlatın; ekranda
   kurulum uyarısı olmamalı. Terminal penceresi kayıt alanında görünmesin.
2. Tarayıcıyı 1920×1080'de tam ekran (F11) açın, yakınlaştırma %100.
3. Önceki denemelerin kaydı görünmesin: rulodaki `Günlüğü temizle`'ye basın (siparişleri
   sıfırlamak için uygulamayı yeniden başlatın).
4. `Bağlantı kontrolü` → `Kontrolleri çalıştır`: tüm satırlar `Geçti` olmalı, rulo tek tek dolar.
5. `Mağaza`: kart numarasının altında banka satırı (Halkbank) ve taksit tablosu görünmeli.
   İsterseniz demo tutarını değiştirip `Tutarı uygula`'ya basın.
6. Öde → ara ekran → `Banka sayfasına geç` → `ONAYLA` → `Ödeme alındı`.
   Rulonun en üstündeki `payments.complete_3ds_payment` satırını açıp maskeyi gösterin.
7. Başarısız akış için yeni bir ödemede banka sayfasında `VAZGEÇ`'e basın.
8. `Siparişler` → `Durumu sorgula`, ardından başarılı ödemede `İade et` → `İadeyi onayla`.
   Aynı gün yapılan iade iptal olarak işlenir; durum `İptal edildi` olur.
9. Kayıttan önce bir kez prova yapın; trdev'de her ödeme gerçek bir test kaydı oluşturur.
