# GEM ZI Checkup

Ilosciowa analiza zmodyfikowanej strategii **Global Equity Momentum (GEM)** w kontekscie polskiego konta **IKE** - z pelnym backtestem, kalibracją kosztow brokerskich i walidacja out-of-sample.

## Po co to jest

Strategia GEM to algorytm rotacyjny: co miesiac wrzucasz 100% kapitalu w jeden ETF - ten, ktory ma najsilniejszy trend (momentum). Gdy rynki spadaja, algorytm automatycznie przenosi kapital do obligacji.

Problem w tym, ze czysta teoria nie uwzglednia **realnych kosztow**: przewalutowania (XTB inkasuje 0.5% na kazdej konwersji PLN/USD), brak akcji ulamkowych (BOSSA, mBank eMakler), podatek Belki, slippage. Ten projekt odpowiada na konkretne pytania:

1. **XTB IKE, BOSSA IKE czy mBank eMakler IKE?** -- co jest lepsze dla strategii rotacyjnej przy regularnych wplatach (DCA)?
2. **Jaki deadband (prog rotacji)?** -- o ile punktow procentowych nowy ETF musi bic obecny, zeby rotacja sie oplacala po kosztach?
3. **Czy dodawac nowe ETF-y** (zloto, small capy, REITs, Europa ex-US)?

## Kluczowe wyniki

| Pytanie | Odpowiedz | Dowod |
|---------|-----------|-------|
| Broker | **BOSSA IKE (promocja)** | XIRR 17.98% vs XTB IKE 17.25% vs mBank eMakler IKE 17.79% (DCA 1000 PLN/mies.) |
| Deadband | **5.4%** (mediana OOS) | IS=6.8%, OOS mediana=5.3%, snap do siatki → 5.4% |
| Wiecej ETF-ow | **Nie** | U5 (Sharpe 1.50) > U7 (1.46) > U9 (1.48); U5 najlepszy XIRR |
| mBank eMaklker vs BOSSA | **BOSSA lepsza** | 0% FX (subkonta) > 0.2% FX mBank eMakler; ale mBank eMakler 0% prowizji na stale |
| Rachunek opodatkowany | **Katastrofa** | XIRR 15.24% vs ~18% IKE (podatek Belki niszczy strategie rotacyjna) |

## Koszyk ETF (U5)

| Ticker | Co to jest | Klasa |
|--------|-----------|-------|
| CNDX.L | iShares NASDAQ 100 | Ryzykowne |
| EIMI.L | iShares MSCI Emerging Markets | Ryzykowne |
| IWDA.L | iShares MSCI World | Ryzykowne |
| IB01.L | iShares Treasury 0-1yr (gotowka) | Bezpieczne |
| CBU0.L | iShares Treasury 7-10yr | Bezpieczne |

## Jak to dziala (algorytm)

```
Co miesiac:
  1. Oblicz momentum = Price[t-1] / Price[t-13] - 1    (pelne 12 mies. zwrotu, skip ostatni miesiac)
  2. Najlepszy ryzykowny ETF = max(momentum CNDX, EIMI, IWDA)
  3. Jesli momentum najlepszego < 0:
       → kup najlepsza obligacje (IB01 lub CBU0)        [risk-off]
     W przeciwnym razie:
       → kup najlepszy ryzykowny ETF                     [risk-on]
  4. Rotuj TYLKO jesli roznica momentum > deadband (5.4%)
     WYJATEK: zmiana rezimu (risk-on ↔ risk-off) -- rotuj bezwarunkowo
```

## Struktura projektu

```
.
├── run_all.py               # Glowny runner -- uruchamia cala analize
├── spec_inputs.yaml         # Konfiguracja parametrow (brokerzy, ETF-y, deadbandy)
├── .env.local               # Szablon zmiennych srodowiskowych (klucz GUS API)
├── .env                     # Twoj klucz API (NIE commitowany, w .gitignore)
├── assumptions.md           # Jawne zalozenia symulacji
├── METODOLOGIA.md           # Pelna dokumentacja techniczna metodologii
├── requirements.txt         # Zaleznosci Python
│
├── src/
│   ├── config.py            # Ladowanie YAML
│   ├── data.py              # Pobieranie danych z Yahoo Finance + CPI z GUS API + build_contribution_schedule
│   ├── momentum.py          # Momentum 13-1 + dual momentum (selekcja celu)
│   ├── broker.py            # Modele kosztowe: XTB, BOSSA, mBank eMakler, rachunek opodatkowany
│   ├── backtest.py          # Glowna petla symulacji (kupno/sprzedaz/koszty/podatki)
│   ├── metrics.py           # XIRR, Sharpe, Sortino, MaxDD, Calmar
│   └── analysis.py          # Sweep deadbandow, walk-forward, timing luck
│
└── results/                 # Wyniki (generowane przez run_all.py)
    ├── decision_memo.md     # Finalna rekomendacja
    ├── baseline_equity_curves.png
    ├── deadband_sweep_comparison.png
    ├── crossover_brokers.png
    ├── universe_comparison.png
    ├── walk_forward_oos.png
    ├── timing_luck.png
    ├── *.csv                # Trade logi, metryki, surowe dane
    └── ...
```

## Konfiguracja

Skopiuj plik `.env.local` do `.env` i wpisz swoj klucz API GUS:

```bash
cp .env.local .env
# Edytuj .env i wstaw prawdziwy klucz z https://api.stat.gov.pl/Home/BdlApi
```

Klucz sluzy do pobierania danych o inflacji CPI (wskaznik srednioroczny) z API Banku Danych Lokalnych GUS. Rejestracja jest darmowa. 

## Uruchomienie

```bash
pip install -r requirements.txt
python -m run_all
```

Wyniki laduja do `results/`. Pierwsze uruchomienie pobiera dane z Yahoo Finance (~1 min), kolejne korzystaja z cache.

## Co dokladnie robi `run_all.py`

| Etap | Co robi | Wynik |
|------|---------|-------|
| 1 | Pobiera dane, waliduje pokrycie | `data_coverage.csv` |
| 2 | Baseline GEM (5 ETF, deadband=0) na 5 brokerach | Krzywe kapitalowe, trade logi |
| 3 | Sweep 41 wartosci deadbandu (0-8%) per broker | Heatmapy XIRR/Sharpe vs deadband |
| 4 | Kalibracja IS (najtanszy IKE, MaxDD + 10% margin) | IS optymalny deadband |
| 6 | Walk-forward (4 foldy OOS), timing luck, czulosc FX | Walidacja odpornosci, mediana OOS |
| 5 | Porownanie koszykow U5 / U7 / U9 (IS + OOS deadband) | Czy dodawac ETF-y |
| 7 | Scenariusze z wplatami, crossover XTB/BOSSA/ mBank eMakler | `decision_memo.md` |

## Modele brokerow

| Parametr | XTB IKE | BOSSA IKE (promocja) | BOSSA IKE (standard) | mBank eMakler IKE | XTB Konto opodatkowane |
|----------|--------:|------------:|---------------:|----------:|-------------:|
| FX per leg (rotacja) | 0.50% | 0.00% | 0.00% | 0.10% | 0.00% |
| FX na wplatach | -- | 0.10% | 0.10% | -- | 0.20% (Walutomat) |
| Prowizja | 0% | 0% (promocja) | 0.29% (min 14 PLN) | 0% (stale) | 0% |
| Slippage | 0.10% | 0.10% | 0.10% | 0.10% | 0.10% |
| Akcje ulamkowe | TAK | NIE | NIE | NIE | TAK |
| Subkonta walut. | NIE | TAK | TAK | NIE | TAK |
| Podatek od zysku | 0% (IKE) | 0% (IKE) | 0% (IKE) | 0% (IKE) | 19% |
| **Koszt rotacji** | **~1.2%** | **~0.2%** | **~0.78%+** | **~0.4%** | **~0.2% + podatek** |

**Uproszczony model kosztów w symulacji:** Backtest używa parametrów z `spec_inputs.yaml` jako celu modelowania, ale **nie odtwarza wszystkich progów taryfowych brokerów**. W szczególności: (a) w przypadku XTB IKE przyjęto prowizję 0% niezależnie od miesięcznego obrotu (ignorując próg 100k EUR/mies. i wyższe stawki), a kluczowym kosztem transakcyjnym poza slippage jest FX per leg = 0,5%; (b) dla mBank eMakler IKE model zakłada 0% prowizji na ETF-y (zgodnie z ofertą „0% na ETF-y”), koncentrując się na koszcie FX 0,1% per leg i braku subkont walutowych. Celem jest przejrzyste porównanie strategii między brokerami bez nadmiernej zależności od szczegółowych, zmiennych progów tabel opłat.

## Testy odpornosci

- **Walk-forward**: 60 mies. trening / 24 mies. test / 4 foldy (nienakl. sie okna). Sredni OOS return: 30.68% (skumulowany, 2-letni), annualizowany: 13.17%.
- **Deadband**: IS optimum=6.8% (informacyjnie, podatny na overfitting). Mediana OOS=5.3%, snap do siatki → **5.4%**.
- **Timing luck**: XIRR od 12.71% do 17.14% w zaleznosci od dnia rebalancingu (std=1.87%).
- **Czulosc FX**: kazde 0.25 pp kosztu FX zjada ~20k-22k PLN wartosci koncowej.
- **Porownanie uniwersow**: U5 > U7 > U9 (wiecej ETF-ow = wiecej rotacji = gorsze wyniki netto).

## Dokumentacja

- [`METODOLOGIA.md`](METODOLOGIA.md) -- pelna dokumentacja techniczna (co, jak i dlaczego jest liczone)
- [`assumptions.md`](assumptions.md) -- jawne zalozenia symulacji
- [`spec_inputs.yaml`](spec_inputs.yaml) -- wszystkie parametry w jednym pliku
- [`results/decision_memo.md`](results/decision_memo.md) -- finalna rekomendacja z liczbami

## Licencja

Projekt edukacyjny. Uzywasz na wlasne ryzyko. To nie jest rekomendacja inwestycyjna.
