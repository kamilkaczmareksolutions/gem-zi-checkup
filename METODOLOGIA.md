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

### 2.1 Obliczanie momentum (13-1)

Dla każdego ETF-a `e_i` w każdym miesiącu `t`:

```
Momentum(e_i, t) = Price(e_i, t-1) / Price(e_i, t-13) - 1
```

Gdzie:
- `Price(e_i, t-1)` = adjusted close sprzed 1 miesiąca (shift o 1 wiersz w dół)
- `Price(e_i, t-13)` = adjusted close sprzed 13 miesięcy (shift o 13 wierszy)

**Ważne:** numerator to cena sprzed 1 miesiąca, nie cena bieżąca. To tzw. "skip-month" — pomija ostatni miesiąc, by uniknąć efektu krótkoterminowego odwrócenia (short-term reversal). Mierzona jest więc stopa zwrotu z pełnych 12 miesięcy: od t-13 do t-1.

Implementacja (dosłownie z kodu):
```python
numerator = prices.shift(1)       # cena sprzed 1 miesiąca
denominator = prices.shift(13)    # cena sprzed 13 miesięcy
momentum = numerator / denominator - 1.0
```

Pierwsze 13 wierszy są NaN (brak wystarczającej historii).

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
Jeśli target == current_holding:
    → nie rób nic

Jeśli target != current_holding:
    oblicz spread = Momentum(target) - Momentum(current_holding)
    
    Jeśli zmiana reżimu (risk-on ↔ risk-off):
        → rotuj BEZWARUNKOWO (deadband nie blokuje)
    
    Jeśli ten sam reżim (np. risky→risky albo safe→safe):
        Jeśli spread >= deadband:
            → rotuj
        Jeśli spread < deadband:
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

### Wybór optymalnego deadbandu — blend IS + OOS

**Kluczowa zasada:** kalibracja deadbandu (IS sweep, walk-forward OOS, blend) odbywa się na **identycznym scenariuszu** jak produkcyjna symulacja: `initial_capital=0`, regularne wpłaty z CPI rewaloryzacją (`fitting_base_contribution_pln` z konfiga, domyślnie 1000 PLN/mies). Benchmark (IWDA.L) jest również porównywany w trybie DCA z tym samym harmonogramem wpłat (bez kosztów).

Finalny deadband jest wyznaczany trójstopniowo, by uniknąć overfittingu do danych historycznych:

1. **Broker referencyjny** — automatycznie wyznaczany jako najtańszy IKE (najwyższa wartość końcowa w baseline DCA). MaxDD strategii jest oceniany na tym brokerze, ponieważ najniższe tarcia kosztowe dają najczystszy obraz "prawdziwego" MaxDD strategii.

2. **IS optymalny** (in-sample) — z siatki deadbandów wybierany jest ten, którego MaxDD na brokerze referencyjnym nie przekracza MaxDD benchmarku DCA (IWDA.L), a jednocześnie daje najwyższy excess XIRR nad benchmarkiem DCA.

3. **Blend z OOS** — walk-forward generuje per fold najlepszy deadband (po Sharpe). Średnia OOS deadbandów (`oos_avg`) jest uśredniana z IS optimum:

```
blended = (IS_optimum + OOS_average) / 2
→ zaokrąglony do najbliższego punktu na siatce testowanych deadbandów
```

Motywacja: sam IS optimum jest podatny na overfitting (np. 6.8% na danych historycznych). OOS średnia (np. 3.0%) pokazuje, co walk-forward faktycznie wybiera na nowych danych. Uśrednienie daje kompromis odporny na overfitting.

**Jeden deadband dla wszystkich brokerów** — strategia momentum jest niezależna od brokera; broker wpływa tylko na koszty, nie na sygnał. Dlatego finalny blended deadband jest stosowany jednolicie.

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

### 4.2 Koszt wpłaty (deposit FX)

Odrębny jednorazowy koszt przewalutowania PLN→waluta ETF-a przy **każdej wpłacie**:
- `deposit_fx_cost` jest odliczany od każdej miesięcznej wpłaty, zanim kapitał trafi do portfela.
- Rotacje (sprzedaż→kupno) **nie ponoszą** tego kosztu, jeśli broker ma subkonta walutowe (BOSSA) lub rachunek operuje w USD (opodatkowany).
- mBank nie ma subkont walutowych, więc każda rotacja wiąże się z FX via `fx_cost_per_leg`.

### 4.3 Profile brokerów

| Parametr | XTB IKE | BOSSA promo | BOSSA standard | mBank IKE | Opodatkowany |
|----------|--------:|------------:|---------------:|----------:|-------------:|
| FX per leg (rotacja) | 0.50% | 0.00% | 0.00% | 0.10% | 0.00% |
| Deposit FX (wpłata) | 0.00% | 0.10% | 0.10% | 0.00% | 0.20% |
| Prowizja | 0.00% | 0.00% | 0.29% (min 14 PLN) | 0.00% | 0.00% |
| Slippage | 0.10% | 0.10% | 0.10% | 0.10% | 0.10% |
| Frakcje | TAK | NIE | NIE | NIE | TAK |
| Podatek | 0% (IKE) | 0% (IKE) | 0% (IKE) | 0% (IKE) | 19% od zysku |
| Subkonta walut. | — | TAK | TAK | NIE | TAK (Walutomat) |
| **Koszt round-trip** | **~1.2%** | **~0.2%** | **~0.78%+** | **~0.4%** | **~0.2% + podatek** |

**Uwaga o XTB IKE:** XTB ma wbudowane 0.5% FX per leg, które jest naliczane przy każdej transakcji (spread walutowy), ale nie ma osobnego kosztu wpłaty — PLN→USD odbywa się automatycznie jako część zlecenia.

**Uwaga o BOSSA IKE:** BOSSA oferuje subkonta walutowe. Rotacje w ramach tej samej waluty (np. sprzedaż ETF-a USD i kupno innego za USD) nie wiążą się z przewalutowaniem. Koszt FX występuje tylko przy wpłacie PLN→USD. Promocja (0% prowizja) ważna do końca 2026.

**Uwaga o mBank IKE:** mBank (eMakler) oferuje 0% prowizji na ETF jako stały element oferty (nie promocja). Koszt FX wynosi 0.1% per leg. Kluczowa różnica vs BOSSA: mBank nie posiada subkont walutowych, więc przy rotacji środki wracają do PLN (sprzedaż), a następnie konwertowane są ponownie na walutę nowego ETF-a (zakup). Łączny koszt FX na rotację: 2 × 0.1% = 0.2%. BOSSA z subkontami walutowymi unika tego kosztu przy rotacjach w ramach jednej waluty.

**Uwaga o rachunku opodatkowanym:** rotacje w USD nie wiążą się z FX (broker z subkontami walutowymi lub XTB). Deposit FX = 0.2% to koszt walutomatu/Revolut przy wpłacie PLN→USD.

### 4.4 Akcje ułamkowe vs pełne jednostki

**XTB / rachunek opodatkowany (frakcje = ON):** `shares = capital / price`, `residual = 0`. Cały kapitał jest zainwestowany.

**BOSSA / mBank (frakcje = OFF):** `shares = floor(capital / price)`, `residual = capital - shares * price`. Reszta leży jako "cash drag" — niepracująca gotówka.

Implementacja:
```python
if self.fractional_shares:
    return capital / price_per_share, 0.0
n = math.floor(capital / price_per_share)
residual = capital - n * price_per_share
return float(n), residual
```

### 4.5 Podatek Belki

Na rachunku opodatkowanym: przy każdej sprzedaży obliczany jest zysk (`sell_proceeds - cost_basis`). Jeśli zysk > 0, potrącane jest 19%. Cost basis to cena zakupu × liczba akcji.

```python
gain = sell_proceeds_gross - cost_basis
tax = gain * 0.19 if gain > 0 else 0.0
net_from_sell = sell_proceeds_gross - sell_cost - tax
```

---

## 5. Przebieg symulacji (pętla główna)

**Kapitał startowy = 0 PLN.** Cały kapitał pochodzi z regularnych wpłat miesięcznych (rewaloryzowanych o CPI). Nie ma lump sum.

Dla każdego miesiąca `t` w zakresie danych:

1. Dodaj wpłatę miesięczną do kapitału (po odliczeniu `deposit_fx_cost`). Przed pierwszym sygnałem momentum (lookback 13 mies.) wpłaty kumulują się jako gotówka.
2. Oblicz momentum dla wszystkich ETF-ów.
3. Wyznacz cel algorytmu (`target`) wg sekcji 2.
4. **Pierwszy miesiąc z sygnałem** (brak holdingu): kup `target` za cały skumulowany kapitał, odlicz koszty kupna, zapisz shares/cash.
5. **Target == obecny holding** lub **deadband blokuje rotację**: zainwestuj wszelki pending capital w obecny ETF (dokupienie).
6. **Target != obecny holding** i deadband nie blokuje: wykonaj rotację.
   - Sprzedaj obecny ETF → odlicz koszt sprzedaży → odlicz podatek (jeśli jest) → otrzymaj `net_from_sell`.
   - Kup nowy ETF za `net_from_sell + cash + capital` → odlicz koszt kupna → oblicz shares i residual.
   - Zapisz jako rotację.
7. Zapisz wartość portfela = `shares * current_price + cash + capital` (capital > 0 tylko gdy brak sygnału).

Wartość portfela jest zapisywana co miesiąc. To tworzy krzywą equity.

**Identyczny scenariusz** (start=0, DCA z CPI) jest używany we wszystkich etapach: baseline, sweep deadbandów, kalibracja IS+OOS, walk-forward, timing luck, benchmark, czułość kosztów. Nie ma rozbieżności między scenariuszem fitowania a scenariuszem produkcyjnym.

---

## 6. Metryki wynikowe

### Główna metryka zwrotu: XIRR (money-weighted)

Przy strategii DCA (regularne wpłaty, start od zera) klasyczny CAGR (`equity[-1]/equity[0]`) jest **bezsensowny** — mała początkowa equity zawyża wynik do absurdalnych 50–60%. Zamiast tego stosujemy **XIRR** (Extended Internal Rate of Return):

```
NPV(r) = Σ CF_i / (1 + r)^(t_i / 365.25) = 0
```

Gdzie:
- `CF_i < 0` = wpłaty inwestora (initial_capital + contribution_schedule)
- `CF_n > 0` = wartość końcowa portfela (terminal value)
- `t_i` = liczba dni od pierwszej wpłaty
- `r` = szukana roczna stopa zwrotu (XIRR)

Solver: `scipy.optimize.brentq` z bracketingiem [-50%, 1000%].

| Metryka | Wzór / opis |
|---------|-------------|
| **XIRR** | Annualizowana money-weighted stopa zwrotu (solver NPV=0) |
| Sharpe | `mean(excess_returns) / std(excess_returns) * sqrt(12)`, rf=0 |
| Sortino | `mean(excess_returns) / downside_std * sqrt(12)` |
| Max Drawdown | `min((equity - cummax) / cummax)` |
| Calmar | `XIRR / |max_drawdown|` |

Sharpe i Sortino liczone na miesięcznych stopach zwrotu krzywej equity (pct_change). Risk-free rate = 0.

### Benchmark

Benchmark = `IWDA.L` (iShares MSCI World), buy-and-hold DCA z tym samym harmonogramem wpłat co strategia GEM (bez kosztów transakcyjnych). Używany do:
- Obliczenia excess XIRR (XIRR strategii - XIRR benchmarku DCA)
- Ograniczenia MaxDD przy selekcji optymalnego deadbandu (MaxDD strategii ≤ MaxDD benchmarku DCA)

---

## 7. Testy odporności

### 7.1 Walk-forward (walidacja out-of-sample)

Procedura (z DCA — ten sam harmonogram wpłat co reszta pipeline'u):
1. Weź okno treningowe = 36 miesięcy (od pozycji `start`).
2. Dla każdego deadbandu z siatki: uruchom backtest DCA na oknie treningowym, policz Sharpe.
3. Wybierz deadband z najwyższym Sharpe na treningu.
4. Uruchom backtest DCA na oknie treningowym + 12 miesięcy testowych. Wytnij equity za okres testowy (OOS).
5. Przesuń `start` o 12 miesięcy. Powtórz.

Wynik: seria foldów. Dla każdego folda znamy:
- jaki deadband został wybrany na treningu,
- jaki return uzyskano OOS (na danych, których algorytm "nie widział" przy wyborze parametru).

Stitching OOS equity: stopy zwrotu z kolejnych foldów są łączone łańcuchowo (wartość startowa = wartość equity z pierwszego folda OOS).

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

Porównanie uniwersów odbywa się na pełnej długości każdego z nich (dłuższe uniwersa mają więcej danych). Porównanie "common window" jest pominięte w trybie DCA, ponieważ obcięcie krzywej equity do wspólnej daty i oderwanie od harmonogramu wpłat prowadzi do błędnych metryk.

---

## 9. Analiza progu przejścia XTB → BOSSA / mBank

Analiza crossover: dla hipotetycznego kapitału jednorazowego ∈ {5k, 10k, 15k, ..., 200k} PLN (lump sum, bez wpłat) porównujemy wartości końcowe między brokerami. Szukany "crossover": najniższy kapitał, od którego BOSSA/mBank daje wyższą wartość końcową niż XTB.

**Uwaga:** ta analiza celowo używa lump sum (nie DCA), bo odpowiada na pytanie "jaki jest minimalny kapitał, przy którym cash drag z braku frakcji nie dominuje?" — niezależnie od tego, jak ten kapitał się tam znalazł.

---

## 10. Scenariusze z wpłatami (Etap 7)

Etap 7 testuje wrażliwość wyniku na kwotę bazowej wpłaty miesięcznej: 500, 1000, 2000 PLN. Kapitał startowy = 0 PLN (tożsamy z resztą pipeline'u).

### Rewaloryzacja o inflację CPI

Na początku każdego roku kalendarzowego wpłata jest rewaloryzowana o wskaźnik średniorocznej inflacji CPI (GUS) za rok poprzedni:

```
wpłata(rok Y) = wpłata(rok Y-1) × (1 + CPI_średnioroczny(Y-1))
```

Dane CPI pobierane są z **GUS BDL API** (zmienna 217230, wskaźnik średnioroczny) i cache'owane lokalnie w `data_cache/cpi_annual_cache.json`. Dla lat jeszcze nieopublikowanych w API (np. bieżący rok) stosowane jest carry-forward ostatniej znanej wartości.

Klucz API przechowywany jest w pliku `.env` (nieśledzony przez git). Szablon: `.env.local`.

### Przebieg

Wpłata (po rewaloryzacji) jest dodawana na początku każdego miesiąca. Jeśli w danym miesiącu następuje rotacja, wpłata jest włączana w kwotę zakupu nowego ETF-a. Jeśli nie ma rotacji i holding się nie zmienia, wpłata jest dodawana do istniejącej pozycji (dokupienie akcji bieżącego ETF-a z uwzględnieniem kosztów kupna i deposit FX).

---

## 11. Znane ograniczenia

1. **Brak modelowania ryzyka walutowego PLN/USD.** Wszystkie ceny są w walucie notowania ETF-a (głównie USD). Symulacja nie konwertuje do PLN — zakłada, że inwestor operuje w walucie instrumentu.

2. **Cena wykonania = adjusted close na koniec miesiąca.** W rzeczywistości zlecenie byłoby wykonane po cenie z dnia złożenia, która może się różnić.

3. **Brak modelowania wpływu na rynek** (market impact). Uzasadnione małym portfelem, ale mogłoby mieć znaczenie przy >1M PLN.

4. **IB01.L ma dane tylko od 2019-02.** Strategia bazowa (U5) efektywnie operuje od ~2020-03 (po 13-miesięcznym lookbacku momentum). Wcześniejsze miesiące korzystają z CBU0.L jako jedynego safe asset.

5. **Walk-forward z krótkim oknem treningowym (36 mies.).** Wynika z ograniczenia danych IB01.L. Idealnie powinno być 60+ miesięcy, ale wtedy zostałoby za mało foldów.

---

## 12. Struktura kodu źródłowego

```
GEMv2/
├── .env.local                   ← szablon zmiennych środowiskowych
├── .env                         ← klucz API GUS (nie w repozytorium, w .gitignore)
├── spec_inputs.yaml             ← konfiguracja parametrów
├── assumptions.md               ← jawne założenia
├── METODOLOGIA.md               ← ten dokument
├── run_all.py                   ← główny runner (uruchom: python -m run_all)
├── src/
│   ├── config.py                ← ładowanie YAML
│   ├── data.py                  ← pobieranie cen (yfinance) + CPI (GUS BDL API)
│   ├── momentum.py              ← obliczanie momentum 13-1 + selekcja celu
│   ├── broker.py                ← modele kosztowe brokerów
│   ├── backtest.py              ← główna pętla symulacji
│   ├── metrics.py               ← XIRR, Sharpe, Sortino, MaxDD, Calmar
│   └── analysis.py              ← sweep deadbandów, walk-forward, timing luck
├── results/                     ← wyniki (wykresy PNG, tabele CSV, decision_memo.md)
└── data_cache/                  ← cache pobranych cen (CSV) + cache CPI (JSON)
```

Aby powtórzyć analizę: `pip install -r requirements.txt && python -m run_all`.
