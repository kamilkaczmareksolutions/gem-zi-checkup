# Rekomendacja końcowa — GEM na IKE

## Stan portfela

- Kapitał: ~9,000 PLN (8k wpłat netto, ~9k obecna wartość)
- Obecny koszyk: U5 (CNDX.L, EIMI.L, IWDA.L, IB01.L, CBU0.L)
- Obecnie wygrywający ETF: EIMI.L
- Broker: XTB IKE
- Okno danych: styczeń 2012 — luty 2026 (170 miesięcy)

---

## 1. Broker: Migruj do BOSSA IKE

### Dowód liczbowy


| Broker                | CAGR (baseline, db=0) | Sharpe   | MaxDD   | Wartość końcowa z 9k |
| --------------------- | --------------------- | -------- | ------- | -------------------- |
| BOSSA IKE (promo)     | **15.33%**            | **1.02** | -23.36% | **58,037 PLN**       |
| BOSSA IKE (standard)  | 14.05%                | 0.95     | -23.50% | 50,020 PLN           |
| XTB IKE               | 13.35%                | 0.90     | -24.17% | 46,031 PLN           |
| Rachunek opodatkowany | 10.30%                | 0.71     | -25.78% | 32,212 PLN           |


**BOSSA (promo) bije XTB o ~12,000 PLN** na identycznej strategii przy 9k kapitału startowego.
Różnica wynika z eliminacji kosztów FX (1% na rotację w XTB vs 0% w BOSSA).

### Analiza progu przejścia (crossover)

BOSSA dominuje XTB **od samego początku** (od 5,000 PLN w górę — najniższy testowany poziom). Nawet cash drag z braku akcji ułamkowych jest mniej destrukcyjny niż 1% koszt FX na każdą rotację.

### Analiza czułości kosztów FX


| Koszt FX (per leg) | CAGR       | Sharpe   | Wartość końcowa |
| ------------------ | ---------- | -------- | --------------- |
| 0.0% (BOSSA)       | 18.50%     | 1.20     | 82,708 PLN      |
| 0.25%              | 17.87%     | 1.16     | 76,912 PLN      |
| **0.50% (XTB)**    | **17.23%** | **1.13** | **71,508 PLN**  |
| 0.75%              | 16.60%     | 1.09     | 66,472 PLN      |
| 1.0%               | 15.97%     | 1.05     | 61,779 PLN      |


Każde 0.25 pp kosztu FX zjada ~5,000-6,000 PLN wartości końcowej przy kapitale 9k.

### Wniosek

**Przenieś strategię do BOSSA IKE.** Brak kosztu FX na subkontach walutowych jest decydujący. Cash drag z braku akcji ułamkowych to problem marginalny przy aktywach wycenianych poniżej ~1000 USD/szt., a Twój portfel jest wystarczająco duży, by kupować pełne jednostki większości ETF-ów.

### Uwaga na podatek Belki

Rachunek opodatkowany traci **~26,000 PLN** vs IKE (na 14 lat, z 9k startowego). IKE jest bezwzględnie lepszym środowiskiem dla strategii rotacyjnej.

---

## 2. Optymalny deadband: 5.2% (statyczny)

### Kalibracja in-sample


| Broker                | Optymalny deadband | Sharpe | CAGR   | MaxDD   | Rotacje |
| --------------------- | ------------------ | ------ | ------ | ------- | ------- |
| XTB IKE               | 5.2%               | 1.13   | 17.23% | -24.17% | 14      |
| BOSSA IKE (promo)     | 5.2%               | 1.20   | 18.37% | -23.35% | 14      |
| BOSSA IKE (standard)  | 5.2%               | 1.16   | 17.58% | -23.70% | 14      |
| Rachunek opodatkowany | 5.2%               | 0.91   | 14.18% | -30.59% | 14      |


Optymalny statyczny deadband = **5.2%** konsekwentnie na wszystkich brokerach. To wyższy próg niż sugerowane w literaturze 2.5-4%, ale dane historyczne potwierdzają, że wyższa bariera chroni lepiej.

### Walidacja Out-of-Sample (Walk-Forward)


| Parametr                      | Wartość    |
| ----------------------------- | ---------- |
| Liczba foldów                 | 11         |
| Średni OOS return per fold    | **11.85%** |
| OOS stitched CAGR             | **10.51%** |
| OOS stitched Sharpe           | 0.74       |
| OOS stitched MaxDD            | -21.92%    |
| Średni wybrany deadband (OOS) | **2.2%**   |


**Kluczowa obserwacja:** Walk-forward wybiera średnio deadband ~2.2%, co jest znacznie niższe niż in-sample optimum 5.2%. To sugeruje, że:

- 5.2% jest prawdopodobnie nieco overfit do danych historycznych,
- OOS CAGR (10.51%) jest niższy niż in-sample (17.23%), co jest normalne,
- **Rozsądny kompromis: deadband w zakresie 3-5%**, dający ochronę bez nadmiernego overfittingu.

### Deadband dynamiczny (zmiennościowy)

Wariant `delta = base + k * sigma(6m)` z k=0.20 daje Sharpe ~0.89-1.00, co jest *gorsze* od statycznego progu. W tym kontekście **statyczny deadband jest wystarczający i prostszy**.

### Rekomendacja

**Ustaw deadband na 4.0%** jako kompromis między in-sample optimum (5.2%) a OOS sygnałem (2.2%).

---

## 3. Uniwersum ETF: Zostań przy U5 (5 ETF-ów)

### Porównanie uniwersów (deadband=5.2%, XTB)


| Uniwersum | Skład                         | CAGR       | Sharpe   | MaxDD       | Rotacje |
| --------- | ----------------------------- | ---------- | -------- | ----------- | ------- |
| **U5**    | CNDX, EIMI, IWDA + IB01, CBU0 | **17.23%** | **1.13** | **-24.17%** | 14      |
| U7        | +IGLN, WSML                   | 12.04%     | 0.79     | -41.13%     | 20      |
| U9        | +IEUX, DPYA                   | 11.51%     | 0.75     | -39.30%     | 20      |


### Dlaczego rozszerzenie szkodzi

1. **Więcej rotacji** (20 vs 14) = więcej kosztów transakcyjnych.
2. **Gorszy max drawdown** (-41% vs -24%) — dodane aktywa (złoto, small cap, REITs) wciągały portfel w nieoptymalny trend.
3. **Niższy Sharpe** we wszystkich rozszerzonych wariantach.

Dodanie złota, small capów, nieruchomości i rynków ex-US **pogarsza** strategię GEM w testowanym okresie. Twój obecny koszyk 5 ETF-ów jest dobrze zbalansowany i nie wymaga rozszerzenia.

### Rekomendacja

**Zostań przy U5.** Nie dodawaj nowych ETF-ów.

---

## 4. Timing luck — wrażliwość na dzień rebalancingu


| Dzień roboczy miesiąca | CAGR       | Sharpe   |
| ---------------------- | ---------- | -------- |
| 1                      | 15.11%     | 0.85     |
| 5                      | 16.48%     | 0.96     |
| **10**                 | **19.03%** | **1.10** |
| 15                     | 18.70%     | 1.02     |
| 20                     | 12.44%     | 0.92     |


Rozstrzał CAGR wynosi **6.6 pp** w zależności od dnia rebalancingu — to ryzyko „timing luck". Rebalancing koło 10-15 dnia roboczego miesiąca daje najlepsze wyniki historyczne. Unikaj rebalancingu na samym końcu/początku miesiąca.

---

## 5. Scenariusze z regularnymi wpłatami


| Wpłata miesięczna | BOSSA promo | BOSSA standard | XTB IKE     | Opodatkowany |
| ----------------- | ----------- | -------------- | ----------- | ------------ |
| 0 PLN             | 81,564      | 74,500         | 71,508      | 50,621       |
| 500 PLN           | 124,777     | 113,839        | 108,974     | 77,412       |
| 1,000 PLN         | 168,465     | 154,003        | 146,440     | 104,203      |
| **2,000 PLN**     | **254,694** | **233,523**    | **221,373** | **157,784**  |


Regularne wpłaty dramatycznie zwiększają wynik. Wpłacając 2,000 PLN/miesiąc na BOSSA promo:

- Start z 9k → końcówka **254,694 PLN** (vs 71,508 bez wpłat na XTB).

---

## 6. Podsumowanie decyzji


| Pytanie            | Odpowiedź                             | Pewność                                     |
| ------------------ | ------------------------------------- | ------------------------------------------- |
| Broker             | **BOSSA IKE**                         | Wysoka — dominuje od 5k PLN                 |
| Deadband           | **4.0%** (kompromis IS/OOS)           | Średnia — OOS wskazuje 2-3%, IS wskazuje 5% |
| Dodatkowe ETF-y    | **Nie — zostań przy U5**              | Wysoka — U7/U9 gorsze                       |
| Dzień rebalancingu | **~10-15 dzień roboczy**              | Średnia — timing luck                       |
| Wpłaty             | **Maksymalizuj** (idealnie limit IKE) | Wysoka                                      |


### Co zrobić teraz

1. **Otwórz konto IKE w BOSSA** i przenieś strategię (uwaga: przeniesienie IKE między brokerami jest możliwe bez utraty parasola podatkowego).
2. **Ustaw deadband na 4%** — nie rotuj ETF-a, chyba że nowy kandydat ma momentum wyższe o co najmniej 4 punkty procentowe.
3. **Nie dodawaj nowych ETF-ów** do koszyka.
4. **Wpłacaj regularnie** na IKE do limitu rocznego (28,260 PLN w 2026).
5. **Rebalancuj** koło 10-15 dnia roboczego miesiąca.

### Warunki zmiany decyzji

- Jeśli BOSSA cofnie promocję 0% prowizji (po lutym 2027), zweryfikuj — ale nawet standardowe 0.29% (min 14 PLN) jest tańsze niż 1% FX drag w XTB.
- Jeśli XTB wprowadzi subkonta walutowe w IKE, przelicz na nowo.
- Deadband: testuj raz w roku na świeżych danych (walk-forward).

