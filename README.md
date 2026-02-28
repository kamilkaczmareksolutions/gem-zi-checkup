# GEM ZI Checkup

Ilosciowa analiza zmodyfikowanej strategii **Global Equity Momentum (GEM)** w kontekscie polskiego konta **IKE** - z pelnym backtestem, kalibracją kosztow brokerskich i walidacja out-of-sample.

## Po co to jest

Strategia GEM to algorytm rotacyjny: co miesiac wrzucasz 100% kapitalu w jeden ETF - ten, ktory ma najsilniejszy trend (momentum). Gdy rynki spadaja, algorytm automatycznie przenosi kapital do obligacji.

Problem w tym, ze czysta teoria nie uwzglednia **realnych kosztow**: przewalutowania (XTB inkasuje 0.5% na kazdej konwersji PLN/USD), brak akcji ulamkowych (BOSSA, mBank), podatek Belki, slippage. Ten projekt odpowiada na konkretne pytania:

1. **XTB IKE, BOSSA IKE czy mBank IKE?** -- co jest lepsze dla strategii rotacyjnej przy malym kapitale (~9k PLN)?
2. **Jaki deadband (prog rotacji)?** -- o ile punktow procentowych nowy ETF musi bic obecny, zeby rotacja sie oplacala po kosztach?
3. **Czy dodawac nowe ETF-y** (zloto, small capy, REITs, Europa ex-US)?

## Kluczowe wyniki

| Pytanie | Odpowiedz | Dowod |
|---------|-----------|-------|
| Broker | **BOSSA IKE (promo)** | 62k vs XTB 46k vs mBank 58k (z 9k startu) |
| Deadband | **6.8%** | IS optimum 6.8% (Sharpe), OOS walk-forward srednia 3.0% |
| Wiecej ETF-ow | **Nie** | U5 (Sharpe 1.13) >> U7 (0.85) >> U9 (0.79) |
| mBank vs BOSSA | **BOSSA lepsza** | 0% FX (subkonta) > 0.2% FX mBank; ale mBank 0% prowizji na stale |
| Rachunek opodatkowany | **Katastrofa** | ~31k vs ~62k IKE (podatek Belki niszczy strategie rotacyjna) |

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
  4. Rotuj TYLKO jesli roznica momentum > deadband (6.8%)
     WYJĄTEK: zmiana rezimu (risk-on ↔ risk-off) -- rotuj bezwarunkowo
```

## Struktura projektu

```
.
├── run_all.py               # Glowny runner -- uruchamia cala analize
├── spec_inputs.yaml         # Konfiguracja parametrow (brokerzy, ETF-y, deadbandy)
├── assumptions.md           # Jawne zalozenia symulacji
├── METODOLOGIA.md           # Pelna dokumentacja techniczna metodologii
├── requirements.txt         # Zaleznosci Python
│
├── src/
│   ├── config.py            # Ladowanie YAML
│   ├── data.py              # Pobieranie danych z Yahoo Finance
│   ├── momentum.py          # Momentum 13-1 + dual momentum (selekcja celu)
│   ├── broker.py            # Modele kosztowe: XTB, BOSSA, mBank, rachunek opodatkowany
│   ├── backtest.py          # Glowna petla symulacji (kupno/sprzedaz/koszty/podatki)
│   ├── metrics.py           # CAGR, Sharpe, Sortino, MaxDD, Calmar
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

## Uruchomienie

```bash
pip install -r requirements.txt
python run_all.py
```

Wyniki laduja do `results/`. Pierwsze uruchomienie pobiera dane z Yahoo Finance (~1 min), kolejne korzystaja z cache.

## Co dokladnie robi `run_all.py`

| Etap | Co robi | Wynik |
|------|---------|-------|
| 1 | Pobiera dane, waliduje pokrycie | `data_coverage.csv` |
| 2 | Baseline GEM (5 ETF, deadband=0) na 5 brokerach | Krzywe kapitalowe, trade logi |
| 3 | Sweep 41 wartosci deadbandu (0-8%) per broker | Heatmapy CAGR/Sharpe vs deadband |
| 4 | Kalibracja statyczna + dynamiczna (zmiennosciowa) | Optymalny deadband per broker |
| 5 | Porownanie koszykow U5 / U7 / U9 | Czy dodawac ETF-y |
| 6 | Walk-forward (11 foldow OOS), timing luck, czulosc FX | Walidacja odpornosci |
| 7 | Scenariusze z wplatami, crossover XTB/BOSSA/mBank | `decision_memo.md` |

## Modele brokerow

| Parametr | XTB IKE | BOSSA promo | BOSSA standard | mBank IKE | Opodatkowany |
|----------|--------:|------------:|---------------:|----------:|-------------:|
| FX per leg (rotacja) | 0.50% | 0.00% | 0.00% | 0.10% | 0.00% |
| FX na wplatach | -- | 0.10% | 0.10% | -- | 0.20% (Walutomat) |
| Prowizja | 0% | 0% (promo) | 0.29% (min 14 PLN) | 0% (stale) | 0% |
| Slippage | 0.10% | 0.10% | 0.10% | 0.10% | 0.10% |
| Akcje ulamkowe | TAK | NIE | NIE | NIE | TAK |
| Subkonta walut. | -- | TAK | TAK | NIE | TAK (Walutomat) |
| Podatek od zysku | 0% (IKE) | 0% (IKE) | 0% (IKE) | 0% (IKE) | 19% |
| **Koszt rotacji** | **~1.2%** | **~0.2%** | **~0.78%+** | **~0.4%** | **~0.2% + podatek** |

## Testy odpornosci

- **Walk-forward**: 36 mies. trening / 12 mies. test / 11 foldow. Sredni OOS return: 12.65%/rok. OOS CAGR: 11.19%.
- **Timing luck**: CAGR od 9.1% do 16.7% w zaleznosci od dnia rebalancingu.
- **Czulosc FX**: kazde 0.25 pp kosztu FX zjada ~4,000-4,500 PLN wartosci koncowej.
- **Porownanie uniwersow**: U5 > U7 > U9 (wiecej ETF-ow = wiecej rotacji = gorsze wyniki).

## Dokumentacja

- [`METODOLOGIA.md`](METODOLOGIA.md) -- pelna dokumentacja techniczna (co, jak i dlaczego jest liczone)
- [`assumptions.md`](assumptions.md) -- jawne zalozenia symulacji
- [`spec_inputs.yaml`](spec_inputs.yaml) -- wszystkie parametry w jednym pliku
- [`results/decision_memo.md`](results/decision_memo.md) -- finalna rekomendacja z liczbami

## Licencja

Projekt edukacyjny. Uzywasz na wlasne ryzyko. To nie jest rekomendacja inwestycyjna.
