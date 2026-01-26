import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import random

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
]

def scrape_yellow_directory():
    """Scrape from free Indian business directory"""

    search_list = [
        ('Interior Designers', 'Ahmedabad'),
        ('Electrician', 'Ahmedabad'),
        ('Plumber', 'Ahmedabad'),
        ('Event Manager', 'Ahmedabad'),
    ]

    leads = []

    for category, city in search_list:
        print(f"\nSearching: {category} in {city}")

        url = f'https://yellow.co.in/search/{category.lower()}+in+{city.lower()}'
        headers = {'User-Agent': random.choice(USER_AGENTS)}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            for listing in soup.find_all('div', class_='listing')[:50]:
                try:
                    name = listing.find('h2', class_='name')
                    phone = listing.find('div', class_='phone')
                    website = listing.find('a', class_='website')

                    if name and website:  # Only if has website
                        lead = {
                            'business_name': name.text.strip(),
                            'phone': phone.text.strip() if phone else '',
                            'website': website['href'],
                            'location': city,
                            'category': category,
                            'source': 'yellow_directory',
                        }
                        leads.append(lead)
                        print(f"  ✓ {lead['business_name']}")
                except:
                    pass

            time.sleep(random.uniform(2, 5))

        except Exception as e:
            print(f"  ✗ Error: {e}")

    add_to_db(leads)

def add_to_db(leads):
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()

    for lead in leads:
        try:
            cursor.execute('''
            INSERT INTO leads (business_name, category, location, phone, website, source, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (lead['business_name'], lead['category'], lead['location'],
                  lead['phone'], lead['website'], lead['source'], 'pending_audit'))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()
    print(f"\n✓ Added {len(leads)} leads to database")

if __name__ == '__main__':
    scrape_yellow_directory()
