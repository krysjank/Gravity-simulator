# Gravity simulator v3.2 – verze pro Python a pygame

Je to přepis projektu ze Scratche `Gravity_simulator_v3.2.sb3`. Program má stejné obrazovky, ovládání, fyziku i grafiku jako originál.

## Spuštění

```
pip install pygame
python main.py
```

Potřebuješ Python 3.8 nebo novější. Složka `assets` musí zůstat vedle souboru `main.py`.

## Ovládání

- **Myš:** tlačítka, posuvníky a přepínače. Před spuštěním simulace můžeš koule přetahovat.
- **Mezerník:** spustí nebo zastaví simulaci.
- **Tlačítko ↻ (reset):** vrátí koule na startovní pozice a nastaví jim původní rychlosti.

## Průběh aplikace

Start → úvod → návod 1/5 až 5/5 (dá se přeskočit tlačítkem *skip*) → „Let's go“ → **hmotnosti** (1–100) → **pohyb ano/ne** → **počáteční rychlosti** (−5 až 5) → **simulace**.

V simulaci otevřeš ozubeným kolečkem **nastavení**:

1. stíny zapnout/vypnout, jejich průhlednost (1–99) a délka (0,2–2 s)
2. zobrazení rychlostí x/y jednotlivých koulí během simulace

## Fyzika (stejná jako v blocích Ball1–Ball3)

Výpočet probíhá 30× za sekundu. Pro každou kouli platí:

```
rychlost += hmotnost_druhé_koule / vzdálenost²   (ve směru k druhé kouli, sečteno přes obě ostatní koule)
poloha   += rychlost
```

- Velikost koule je `hmotnost × 1,5 + 50 %`.
- Když se koule dotkne jiné koule, zastaví se.
- Stejně jako ve Scratchi nemůže koule úplně opustit scénu.

## Co můžeš snadno změnit (začátek souboru `main.py`)

- `SCALE`: velikost okna. Hodnota 2 znamená 960 × 720, hodnota 1 původních 480 × 360.
- `DEFAULT_MASS`, `START_POS`: výchozí hmotnosti a startovní pozice koulí.

## Struktura

- `main.py`: celý program, rozdělený do tříd
  - `Costume`, `Sprite`, `Button`: kostýmy a sprajty jako ve Scratchi
  - `Monitor`: zobrazení proměnných (posuvníky a čísla)
  - `Ball`, `gravity_acceleration`: fyzika
  - `Game`: obrazovky a přechody mezi nimi (`enter`, `go`), simulace a vykreslování
- `assets/`: kostýmy převedené ze SVG do PNG, `costumes.json` se středy kostýmů a font pro monitory (Noto Sans, licence OFL)
