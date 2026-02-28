# Metodologia symulacji GEM na IKE — dokumentacja techniczna

## 1. Dane wejściowe

### Źródło
Yahoo Finance (`yfinance`), pole `Close` z flagą `auto_adjust=True` (ceny skorygowane o splity i dywidendy).

### Próbkowanie
Dane dzienne resamplowane do **ostatniego dnia roboczego miesiąca** (pandas `BME` — Business Month End). Każdy wiersz wynikowego DataFrame to jedna obserwacja miesięczna — cena zamknięcia z ostatniego dnia handlowego danego miesiąca.

### Okres
2012-01-01 do 2026-02-28. Pokrycie jest nierównomierne — ETF-y mają różne daty startu:

| Ticker | Start | Opis |
|--------|-------|------|
| CNDX.L | 2012-01 | iShares NASDAQ 100 |
| IWDA.L | 2012-01 | iShares MSCI World |
| CBU0.L | 2012-01 | iShares Treasury 7-10yr |
| IGLN.L | 2012-01 | iShares Physical Gold |
| IEUX.L | 2012-01 | iShares MSCI Europe |
| EIMI.L | 2014-05 | iShares MSCI EM IMI |
| WSML.L | 2018-03 | iShares MSCI World Small Cap |
| DPYA.L | 2018-05 | iShares Dev Markets Property |
| IB01.L | 2019-02 | iShares Treasury 0-1yr |

Symulacja **nie wymaga**, by wszystkie ETF-y miały dane od tego samego dnia. Algorytm w danym miesiącu pracuje tylko na tickerach, które mają dostępne dane (non-NaN). ETF, który jeszcze nie istnieje, jest po prostu pomijany w rankingu.

### Podział na klasy aktywów

Każdy ETF jest przypisany do jednej z dwóch klas:

- **Risky** (ryzykowne): CNDX.L, EIMI.L, IWDA.L, IGLN.L, WSML.L, IEUX.L, DPYA.L
- **Safe** (bezpieczne): IB01.L, CBU0.L

Podział ten jest kluczowy dla filtra absolute momentum (patrz sekcja 2.2).

---

## 2. Sygnał momentum

### 2.1 Obliczanie momentum (12-1)

Dla każdego ETF-a `e_i` w każdym miesiącu `t`:

```
Momentum(e_i, t) = Price(e_i, t-1) / Price(e_i, t-12) - 1
```

Gdzie:
- `Price(e_i, t-1)` = adjusted close sprzed 1 miesiąca (shift o 1 wiersz w dół)
- `Price(e_i, t-12)` = adjusted close sprzed 12 miesięcy (shift o 12 wierszy)

**Ważne:** numerator to cena sprzed 1 miesiąca, nie cena bieżąca. To tzw. "skip-month" — pomija ostatni miesiąc, by uniknąć efektu krótkoterminowego odwrócenia (short-term reversal). Mierzona jest więc stopa zwrotu z okresu od t-12 do t-1 (11 miesięcy wstecz, ale zaczęte 12 miesięcy temu).

Implementacja (dosłownie z kodu):
```python
numerator = prices.shift(1)       # cena sprzed 1 miesiąca
denominator = prices.shift(12)    # cena sprzed 12 miesięcy
momentum = numerator / denominator - 1.0
```

Pierwsze 12 wierszy są NaN (brak wystarczającej historii).

### 2.2 Selekcja celu — dual momentum

W każdym miesiącu algorytm wykonuje dwa kroki:

**Krok A — Cross-sectional momentum (ranking):**
Spośród ETF-ów klasy *risky* wybierz ten z najwyższym momentum. Nazwijmy go `best_risky`.

**Krok B — Absolute momentum (filtr):**
Sprawdź, czy `Momentum(best_risky) >= 0`:
- **TAK** (risk-on): cel = `best_risky`
- **NIE** (risk-off): cel = ETF z klasy *safe* o najwyższym momentum

To jest filtr ochrony kapitału: jeśli nawet najlepsze ryzykowne aktywo ma ujemny trend, algorytm ucieka do obligacji.

**Implementacja kluczowego warunku** (dosłownie z kodu):
```python
if best_risky_val < 0:
    # absolute momentum filter: risk-off
    target = safe_mom.idxmax()  # najlepsza obligacja
else:
    target = best_risky         # najlepsze ryzykowne aktywo
```

---

## 3. Reguła deadbandu (progu rotacji)

### Logika decyzji o rotacji

W każdym miesiącu, po wyznaczeniu celu (`target`), algorytm sprawdza warunki rotacji:

```
JEśli target == current_holding:
    → nie rób nic

JEśli target != current_holding:
    oblicz spread = Momentum(target) - Momentum(current_holding)
    
    JEśli zmiana reżimu (risk-on ↔ risk-off):
        → rotuj BEZWARUNKOWO (deadband nie blokuje)
    
    JEśli ten sam reżim (np. risky→risky albo safe→safe):
        JEśli spread >= deadband:
            → rotuj
        JEśli spread < deadband:
            → nie rób nic (zostań w obecnym ETF)
```

**Kluczowa decyzja projektowa:** przejścia między reżimami (np. z akcji do obligacji, gdy rynek spada) **omijają deadband**. Deadband blokuje tylko rotacje wewnątrz tej samej klasy (np. przeskok z CNDX na IWDA, gdy różnica momentum jest mała).

Implementacja (dosłownie z kodu):
```python
was_risk_off = current_holding in safe
going_risk_off = sig["is_risk_off"]
regime_change = was_risk_off != going_risk_off

if not regime_change and spread < deadband:
    # insufficient spread -> hold
    continue
```

### Testowane warianty deadbandu

**Statyczny:** siatka od 0.0% do 8.0% co 0.2 pp (41 punktów).

**Dynamiczny:** `delta = base + k * sigma_avg(6m)`, gdzie:
- `base` = 2.0%
- `k` ∈ {0.05, 0.10, 0.15, 0.20}
- `sigma_avg(6m)` = średnie 6-miesięczne odchylenie standardowe miesięcznych stóp zwrotu, uśrednione po wszystkich ETF-ach w koszyku

---

## 4. Model kosztów i egzekucji (broker)

Każdy broker ma osobny profil kosztowy. Koszty są odliczane **od kapitału w momencie transakcji**, nie na koniec okresu.

### 4.1 Struktura kosztu pojedynczej transakcji

Koszt procentowy jednej operacji (kupna LUB sprzedaży):

```
koszt_pct = fx_cost_per_leg + slippage + commission_frac
```

Gdzie `commission_frac = max(trade_value * commission_pct, commission_min_pln) / trade_value`.

Dla pełnej rotacji (sprzedaj stary + kup nowy) koszt jest naliczany **dwukrotnie** — osobno na sprzedaży, osobno na kupnie.

### 4.2 Profile brokerów

| Parametr | XTB IKE | BOSSA promo | BOSSA standard | Opodatkowany |
|----------|--------:|------------:|---------------:|-------------:|
| FX per leg | 0.50% | 0.00% | 0.00% | 0.50% |
| Prowizja | 0.00% | 0.00% | 0.29% (min 14 PLN) | 0.00% |
| Slippage | 0.10% | 0.10% | 0.10% | 0.10% |
| Frakcje | TAK | NIE | NIE | TAK |
| Podatek | 0% (IKE) | 0% (IKE) | 0% (IKE) | 19% od zysku |
| **Koszt round-trip** | **~1.2%** | **~0.2%** | **~0.78%+** | **~1.2% + podatek** |

### 4.3 Akcje ułamkowe vs pełne jednostki

**XTB (frakcje = ON):** `shares = capital / price`, `residual = 0`. Cały kapitał jest zainwestowany.

**BOSSA (frakcje = OFF):** `shares = floor(capital / price)`, `residual = capital - shares * price`. Reszta leży jako "cash drag" — niepracująca gotówka.

Implementacja:
```python
if self.fractional_shares:
    return capital / price_per_share, 0.0
n = math.floor(capital / price_per_share)
residual = capital - n * price_per_share
return float(n), residual
```

### 4.4 Podatek Belki

Na rachunku opodatkowanym: przy każdej sprzedaży obliczany jest zysk (`sell_proceeds - cost_basis`). Jeśli zysk > 0, potrącane jest 19%. Cost basis to cena zakupu * liczba akcji.

```python
gain = sell_proceeds_gross - cost_basis
tax = gain * 0.19 if gain > 0 else 0.0
net_from_sell = sell_proceeds_gross - sell_cost - tax
```

---

## 5. Przebieg symulacji (pętla główna)

Dla każdego miesiąca `t` w zakresie danych:

1. Dodaj ewentualną wpłatę miesięczną do kapitału.
2. Oblicz momentum dla wszystkich ETF-ów.
3. Wyznacz cel algorytmu (`target`) wg sekcji 2.
4. **Pierwszy miesiąc** (brak holdingu): kup `target`, odlicz koszty kupna, zapisz shares/cash.
5. **Target == obecny holding**: nie rób nic.
6. **Target != obecny holding**: sprawdź deadband (sekcja 3).
   - Jeśli rotacja dozwolona:
     a. Sprzedaj obecny ETF → odlicz koszt sprzedaży → odlicz podatek (jeśli jest) → otrzymaj `net_from_sell`.
     b. Kup nowy ETF za `net_from_sell + cash` → odlicz koszt kupna → oblicz shares i residual.
     c. Zapisz jako rotację.
   - Jeśli deadband blokuje: nie rób nic.
7. Zapisz wartość portfela = `shares * current_price + cash`.

Wartość portfela jest zapisywana co miesiąc. To tworzy krzywą equity.

---

## 6. Metryki wynikowe

| Metryka | Wzór |
|---------|------|
| Total Return | `equity[-1] / equity[0] - 1` |
| CAGR | `(equity[-1] / equity[0])^(1/years) - 1`, years = dni/365.25 |
| Sharpe | `mean(excess_returns) / std(excess_returns) * sqrt(12)`, rf=0 |
| Sortino | `mean(excess_returns) / downside_std * sqrt(12)` |
| Max Drawdown | `min((equity - cummax) / cummax)` |
| Calmar | `CAGR / |max_drawdown|` |

Wszystkie metryki liczone na miesięcznych stopach zwrotu krzywej equity. Sharpe i Sortino annualizowane mnożnikiem `sqrt(12)`. Risk-free rate = 0 (uproszczenie).

---

## 7. Testy odporności

### 7.1 Walk-forward (walidacja out-of-sample)

Procedura:
1. Weź okno treningowe = 36 miesięcy (od pozycji `start`).
2. Dla każdego deadbandu z siatki: uruchom backtest na oknie treningowym, policz Sharpe.
3. Wybierz deadband z najwyższym Sharpe na treningu.
4. Uruchom backtest na oknie treningowym + 12 miesięcy testowych. Wytnij equity za okres testowy (OOS).
5. Przesuń `start` o 12 miesięcy. Powtórz.

Wynik: 11 foldów. Dla każdego folda znamy:
- jaki deadband został wybrany na treningu,
- jaki return uzyskano OOS (na danych, których algorytm "nie widział" przy wyborze parametru).

Stitching OOS equity: stopy zwrotu z kolejnych foldów są łączone łańcuchowo (wartość końcowa folda N = wartość startowa folda N+1).

### 7.2 Timing luck

Zamiast resamplować dane do końca miesiąca, bierzemy N-ty dzień roboczy każdego miesiąca (N ∈ {1, 5, 10, 15, 20}). Dla każdego N uruchamiamy pełny backtest i porównujemy metryki.

Cel: zmierzyć, ile wyniku zależy od arbitralnego wyboru dnia rebalancingu.

### 7.3 Czułość na koszty FX

FX per leg ∈ {0.0%, 0.25%, 0.50%, 0.75%, 1.0%}. Reszta parametrów stała. Cel: zmierzyć elastyczność wyniku na koszt przewalutowania.

---

## 8. Porównanie uniwersów ETF

Trzy warianty koszyka:

| Wariant | ETF-y risky | ETF-y safe |
|---------|-------------|------------|
| **U5** | CNDX.L, EIMI.L, IWDA.L | IB01.L, CBU0.L |
| **U7** | U5 + IGLN.L (złoto), WSML.L (small cap) | IB01.L, CBU0.L |
| **U9** | U7 + IEUX.L (Europa), DPYA.L (REITs) | IB01.L, CBU0.L |

Każdy wariant testowany identycznie (ten sam deadband, ten sam broker, ten sam backtest).

Dodatkowe porównanie "common window": obcięcie krzywych equity do wspólnej daty startowej i renormalizacja do kapitału początkowego, by CAGR był porównywalny pomimo różnych dat startu poszczególnych ETF-ów.

---

## 9. Analiza progu przejścia XTB → BOSSA

Dla kapitału początkowego ∈ {5k, 10k, 15k, ..., 200k} PLN:
- uruchom backtest na XTB IKE z optymalnym deadbandem,
- uruchom backtest na BOSSA IKE (promo) z optymalnym deadbandem,
- porównaj wartości końcowe.

Szukany "crossover": najniższy kapitał, od którego BOSSA daje wyższą wartość końcową niż XTB.

---

## 10. Scenariusze z wpłatami

Wpłata miesięczna ∈ {0, 500, 1000, 2000} PLN. Kapitał jest dodawany na początku każdego miesiąca. Jeśli w danym miesiącu następuje rotacja, nowa wpłata jest włączana w kwotę zakupu nowego ETF-a. Jeśli nie ma rotacji i holding się nie zmienia, wpłata jest dodawana do istniejącej pozycji (dokupienie akcji bieżącego ETF-a z uwzględnieniem kosztów kupna).

---

## 11. Znane ograniczenia

1. **Brak modelowania ryzyka walutowego PLN/USD.** Wszystkie ceny są w walucie notowania ETF-a (głównie USD). Symulacja nie konwertuje do PLN — zakłada, że inwestor operuje w walucie instrumentu.

2. **Cena wykonania = adjusted close na koniec miesiąca.** W rzeczywistości zlecenie byłoby wykonane po cenie z dnia złożenia, która może się różnić.

3. **Brak modelowania wpływu na rynek** (market impact). Uzasadnione małym portfelem (9k PLN), ale mogłoby mieć znaczenie przy >1M PLN.

4. **BOSSA — uproszczenie FX.** Zakładamy, że kapitał już rezyduje na subkoncie walutowym (USD). W praktyce pierwsza wpłata w PLN wymaga jednorazowego przewalutowania (3 darmowe konwersje/rok w BOSSA).

5. **IB01.L ma dane tylko od 2019-02.** Strategia bazowa (U5) efektywnie operuje od ~2020-02 (po 12-miesięcznym lookbacku momentum). Wcześniejsze miesiące korzystają z CBU0.L jako jedynego safe asset.

6. **Walk-forward z krótkim oknem treningowym (36 mies.).** Wynika z ograniczenia danych IB01.L. Idealnie powinno być 60+ miesięcy, ale wtedy zostałoby za mało foldów.

---

## 12. Struktura kodu źródłowego

```
GEMv2/
├── spec_inputs.yaml          ← konfiguracja parametrów
├── assumptions.md            ← jawne założenia
├── METODOLOGIA.md            ← ten dokument
├── run_all.py                ← główny runner (uruchom: python run_all.py)
├── src/
│   ├── config.py             ← ładowanie YAML
│   ├── data.py               ← pobieranie i czyszczenie danych (yfinance)
│   ├── momentum.py           ← obliczanie momentum 12-1 + selekcja celu
│   ├── broker.py             ← modele kosztowe brokerów
│   ├── backtest.py           ← główna pętla symulacji
│   ├── metrics.py            ← CAGR, Sharpe, Sortino, MaxDD, Calmar
│   └── analysis.py           ← sweep deadbandów, walk-forward, timing luck
├── results/                  ← wyniki (wykresy PNG, tabele CSV, decision_memo.md)
└── data_cache/               ← cache pobranych cen (CSV)
```

Aby powtórzyć analizę: `pip install -r requirements.txt && python run_all.py`.
