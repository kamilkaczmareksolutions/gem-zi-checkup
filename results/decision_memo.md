# Rekomendacja końcowa — GEM na IKE

## Stan portfela
- Kapitał: 0 PLN
- Obecny koszyk: U5 (IUIT.L, EIMI.L, IWDA.L, IB01.L, CBU0.L)
- Obecnie wygrywający ETF: EIMI.L

## 1. Broker: BOSSA IKE (promo)

Przy kapitale 0 PLN, najlepszy wynik końcowy daje BOSSA IKE (promo) (XTB IKE=501523 PLN, BOSSA IKE (promo)=570659 PLN, mBank IKE (eMakler)=556413 PLN).

### Porównanie modeli kosztowych

| Broker | FX/leg | Prowizja | Frakcje | Uwagi |
|--------|--------|----------|---------|-------|
| XTB IKE | 0.5% | 0% | Tak | Wysoki FX, brak cash drag |
| BOSSA IKE (promo) | 0% | 0% (promo) | Nie | Subkonta walutowe, promo do 2027 |
| mBank IKE (eMakler) | 0.1% | 0% (stale) | Nie | Brak subkont walutowych, FX na obu nogach rotacji |

### Warunki migracji
- BOSSA IKE (promo) > XTB od kapitału ~5,000 PLN
- mBank IKE (eMakler) > XTB od kapitału ~5,000 PLN

## Benchmark: IWDA.L (pasywny DCA)
- XIRR: 12.27%
- MaxDD: -20.23%
- Wartość końcowa: 470,059 PLN

## 2. Optymalny deadband

**Wynik: deadband = 0.016 (1.6%)** (jednakowy dla wszystkich brokerów)

### Jak obliczono:
1. **Broker referencyjny**: BOSSA IKE (promo) (najtańszy IKE — najniższe tarcia kosztowe)
2. **IS optymalny** (informacyjnie): 0.076 (7.6%) — górna granica rozsądnego deadbandu;
najwyższy excess XIRR spośród deadbandów, których MaxDD nie przekracza MaxDD benchmarku + 10% margin.
Nie używany bezpośrednio do rekomendacji — podatny na look-ahead bias.
3. **OOS średnia** (walk-forward): 0.016 (1.6%)
4. **OOS mediana** (walk-forward): 0.017 (1.7%)
5. **Rekomendowany deadband** = 0.0170
   → zaokrąglony do siatki: **0.016 (1.6%)**

### Wyniki per broker @ deadband = 0.016

| Broker | Excess XIRR | MaxDD | Sharpe (IS) |
|--------|-------------|-------|--------|
| XTB IKE | +4.10% | -24.89% | 1.46 |
| BOSSA IKE (promo) | +5.72% | -25.02% | 1.49 |
| mBank IKE (eMakler) | +5.41% | -24.99% | 1.48 |

## 3. Uniwersum ETF

Rekomendowane: **U9**
U9 (9 ETF-ów): Sharpe=1.47, XIRR=15.79% (testowane przy IS deadband=7.6%)

**Przy rekomendowanym deadband=1.6% (OOS):** U9(9 ETF-ów): Sharpe=1.52, XIRR=18.51%

## 4. Walidacja Out-of-Sample

Średni OOS return per fold (skumulowany, 2-letni): 42.78%. Annualizowany: 18.50%
Wybrane deadbandy per fold: ['0.030', '0.030', '0.000', '0.004']

## 5. Scenariusze z regularnymi wpłatami (kapitał startowy = 0, CPI rewaloryzacja)

Wpłaty co miesiąc, rewaloryzowane o wskaźnik średniorocznej inflacji CPI (GUS) na początku każdego roku.
Kapitał startowy = 0 PLN.

### Wartość końcowa portfela

|   wpłata bazowa (PLN/mies.) |   bossa_ike_promo |   bossa_ike_standard |   mbank_ike |   taxed_account |   xtb_ike |
|----------------------------:|------------------:|---------------------:|------------:|----------------:|----------:|
|                         500 |           292,925 |              267,893 |     286,428 |         235,209 |   261,198 |
|                        1000 |           586,027 |              542,638 |     573,095 |         470,419 |   522,396 |
|                        2000 |         1,172,326 |            1,091,952 |   1,146,479 |         940,837 | 1,044,790 |

### Suma wpłat i rewaloryzacja

| Wpłata bazowa | Wpłata końcowa (po CPI) | Suma wpłat |
|:---:|:---:|:---:|
| 500 PLN | 783 PLN | 88,818 PLN |
| 1000 PLN | 1566 PLN | 177,635 PLN |
| 2000 PLN | 3133 PLN | 355,270 PLN |


## Podsumowanie decyzji

1. **Wybierz brokera** wg powyższej tabeli kosztowej i progu crossover.
2. **Ustaw deadband** na **1.6%**.
3. **Rozważ rozszerzenie koszyka** jeśli dane OOS to potwierdzają.
4. **Regularnie wpłacaj** — nawet małe kwoty znacząco podnoszą wartość końcową dzięki procentowi składanemu w parasolu IKE.
