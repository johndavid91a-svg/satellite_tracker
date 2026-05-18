"""
Test script to verify Indian launch highlighting logic
"""

# Test data simulating launches
test_launches = [
    {"country": "IND", "agency": "ISRO", "name": "PSLV-C58 | XPoSat"},
    {"country": "USA", "agency": "SpaceX", "name": "Falcon 9 | Starlink"},
    {"country": "India", "agency": "ISRO", "name": "GSLV Mk III | Chandrayaan-4"},
    {"country": "CHN", "agency": "CASC", "name": "Long March 5 | Space Station"},
    {"country": "USA", "agency": "Indian Space Research Organisation", "name": "Test Launch"},
]

def is_indian_launch(launch):
    """Check if a launch is Indian"""
    return launch['country'] in ['IND', 'India'] or 'India' in launch['agency']

print("Testing Indian Launch Detection:")
print("=" * 60)

for i, launch in enumerate(test_launches, 1):
    is_indian = is_indian_launch(launch)
    marker = "⭐🇮🇳" if is_indian else "  "
    status = "✅ DETECTED" if is_indian else "❌ Not Indian"
    
    print(f"\n{i}. {marker} {launch['name']}")
    print(f"   Country: {launch['country']} | Agency: {launch['agency']}")
    print(f"   Status: {status}")

print("\n" + "=" * 60)
print("\nExpected Results:")
print("✅ Launch 1: PSLV-C58 (country=IND)")
print("✅ Launch 3: GSLV Mk III (country=India)")
print("✅ Launch 5: Test Launch (agency contains 'India')")
print("❌ Launch 2: Falcon 9 (USA)")
print("❌ Launch 4: Long March 5 (China)")

# Test sorting
print("\n" + "=" * 60)
print("Testing Sort Priority (Indian launches first):")
print("=" * 60)

sorted_launches = sorted(test_launches, key=lambda x: (not is_indian_launch(x), x['name']))

for i, launch in enumerate(sorted_launches, 1):
    is_indian = is_indian_launch(launch)
    marker = "⭐🇮🇳" if is_indian else "  "
    print(f"{i}. {marker} {launch['name']}")

print("\n✅ Test complete! Indian launches should appear first (1-3).")
