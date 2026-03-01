# Rekomendacja końcowa — GEM na IKE

## Stan portfela
- Kapitał: 0 PLN
- Obecny koszyk: U5 (CNDX.L, EIMI.L, IWDA.L, IB01.L, CBU0.L)
- Obecnie wygrywający ETF: EIMI.L

## 1. Broker: BOSSA IKE (promo)

Przy kapitale 0 PLN, najlepszy wynik końcowy daje BOSSA IKE (promo) (XTB IKE=427719 PLN, BOSSA IKE (promo)=515817 PLN, mBank IKE (eMakler)=495752 PLN).

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

## 2. Optymalny deadband — metodologia blend IS + OOS

**Wynik: deadband = 0.046 (4.6%)** (jednakowy dla wszystkich brokerów)

### Jak obliczono:
1. **Broker referencyjny**: BOSSA IKE (promo) (najtańszy IKE — najniższe tarcia kosztowe)
2. **IS optymalny** (in-sample): 0.068 (6.8%) — najwyższy excess XIRR
   spośród deadbandów, których MaxDD na brokerze referencyjnym nie przekracza MaxDD benchmarku + 10% margin
3. **OOS średnia** (walk-forward): 0.024 (2.4%)
4. **OOS mediana** (walk-forward): 0.014 (1.4%)
5. **Blend** = (IS optymalny + OOS średnia) / 2 = (0.068 + 0.024) / 2 = 0.0462
   → zaokrąglony do siatki: **0.046 (4.6%)**

Dlaczego blend: sam IS optymalny (6.8%) jest podatny na overfitting do danych
historycznych. OOS średnia (2.4%) pokazuje, co faktycznie wybiera walk-forward
na nowych danych. Uśrednienie daje kompromis odporny na overfitting.

### Wyniki per broker @ deadband = 0.046

| Broker | Excess XIRR | MaxDD | Sharpe |
|--------|-------------|-------|--------|
| XTB IKE | +0.59% | -21.93% | 1.44 |
| BOSSA IKE (promo) | +1.67% | -21.14% | 1.46 |
| mBank IKE (eMakler) | +1.40% | -21.23% | 1.46 |

## 3. Uniwersum ETF

Rekomendowane: **U5**
U5 (5 ETF-ów): Sharpe=1.50, XIRR=15.62% (testowane przy IS deadband=6.8%)

## 4. Walidacja Out-of-Sample

Średni OOS return per fold: 14.64%.
Wybrane deadbandy per fold: ['0.000', '0.000', '0.050', '0.014', '0.054', '0.014', '0.000', '0.068', '0.068', '0.000', '0.000']

## 5. Scenariusze z regularnymi wpłatami (kapitał startowy = 0, CPI rewaloryzacja)

Wpłaty co miesiąc, rewaloryzowane o wskaźnik średniorocznej inflacji CPI (GUS) na początku każdego roku.
Kapitał startowy = 0 PLN.

### Wartość końcowa portfela

|   wpłata bazowa (PLN/mies.) |   bossa_ike_promo |   bossa_ike_standard |   mbank_ike |   taxed_account |   xtb_ike |
|----------------------------:|------------------:|---------------------:|------------:|----------------:|----------:|
|                         500 |           251,160 |              231,015 |     245,863 |         211,205 |   237,029 |
|                        1000 |           515,400 |              480,555 |     505,529 |         422,410 |   474,059 |
|                        2000 |         1,037,773 |              973,512 |   1,017,331 |         844,820 |   948,117 |

### Suma wpłat i rewaloryzacja

| Wpłata bazowa | Wpłata końcowa (po CPI) | Suma wpłat |
|:---:|:---:|:---:|
| 500 PLN | 783 PLN | 88,818 PLN |
| 1000 PLN | 1566 PLN | 177,635 PLN |
| 2000 PLN | 3133 PLN | 355,270 PLN |


## Podsumowanie decyzji

1. **Wybierz brokera** wg powyższej tabeli kosztowej i progu crossover.
2. **Ustaw deadband** na **4.6%** (blend IS + OOS, odporny na overfitting).
3. **Rozważ rozszerzenie koszyka** jeśli dane OOS to potwierdzają.
4. **Regularnie wpłacaj** — nawet małe kwoty znacząco podnoszą wartość końcową dzięki procentowi składanemu w parasolu IKE.
