import sys
from pathlib import Path
import time

# Ensure Python can find your local modules
# ROOT = Path(__file__).parent
# sys.path.insert(0, str(ROOT))

from pipeline.ner import AddressExtractor

def run_ner_tests():
    print(" [⚙️] Loading AddressExtractor...")
    try:
        extractor = AddressExtractor.load()
    except FileNotFoundError as e:
        print(f" [❌] Error: {e}")
        print("Make sure your 'address_ner_crf.pkl' and dictionary text files are in the right folders!")
        return

    # ---------------------------------------------------------
    # MOCK DATA: Curated edge cases for Kyiv urban monitoring
    # ---------------------------------------------------------
    mock_messages = [
        # 1. Standard Address
        "Сьогодні сталася масштабна ДТП на вулиці Хрещатик, 24. Рух ускладнено.",
        
        # 2. Metro Station (Abbreviated)
        "Увага! Через повідомлення про мінування тимчасово закрито ст. м. Театральна та Золоті Ворота.",
        
        # 3. Intersections (Very common in traffic news)
        "Великий затор утворився на розі проспекту Берестейського та вулиці Чорновола.",
        
        # 4. District / Broad Area
        "Завтра в Голосіївському районі та на Печерську очікуються планові відключення світла.",
        
        # 5. Non-standard abbreviations and numbers
        "Ремонтні роботи триватимуть на просп. Науки 11-А до пізнього вечора.",
        
        # 6. Bridge / Infrastructure
        "На Північному мосту частково перекрито рух через ремонт деформаційного шва.",
        
        # 7. Negative Test (No address present)
        "Завтра по всій території країни очікується сильний дощ та шквальний вітер. Будьте обережні!",
        
        # 8. Complex multi-address sentence
        "Аварія на водопроводі: без води залишилися будинки по вул. Антоновича 45, 47, 49 та вул. Велика Васильківська 50."
    ]

    print("\n [🚀] Starting NER Tests...\n" + "-"*50)
    
    total_time = 0

    for i, text in enumerate(mock_messages, 1):
        print(f"Test {i}: {text}")
        
        # Run the prediction
        t0 = time.perf_counter()
        result = extractor.predict(text)
        elapsed = (time.perf_counter() - t0) * 1000
        total_time += elapsed

        # Format the output
        if result.address:
            print(f"  ✅ Знайдено ({len(result.address)}):")
            for span in result.address:
                print(f"     - '{span.text}' (Впевненість: {span.confidence:.2f})")
        else:
            print("  ❌ Адрес не знайдено (Negative Test)")
            
        print(f"  ⏱ Час: {elapsed:.2f}ms\n" + "-"*50)

    print(f"\n [🏁] Усі тести завершено за {total_time:.2f}ms")

if __name__ == "__main__":
    run_ner_tests()