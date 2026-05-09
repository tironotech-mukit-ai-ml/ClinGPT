"""
Post-installation script for InTEAM AI Service
Automatically installs Spacy model after pip install
"""
import subprocess
import sys


def install_spacy_model():
    """Install the Spacy en_core_web_lg model"""
    print("\n" + "="*60)
    print("Installing Spacy model: en_core_web_lg")
    print("This downloads ~400MB and may take 3-5 minutes...")
    print("="*60 + "\n")
    
    try:
        subprocess.check_call([
            sys.executable, 
            "-m", 
            "spacy", 
            "download", 
            "en_core_web_lg"
        ])
        
        print("\n" + "="*60)
        print("✅ Spacy model installed successfully!")
        print("="*60 + "\n")
        
    except subprocess.CalledProcessError as e:
        print("\n" + "="*60)
        print("⚠️  Spacy model installation failed!")
        print("You can install it manually with:")
        print("  python -m spacy download en_core_web_lg")
        print("="*60 + "\n")
        # Don't fail the entire installation
        pass


if __name__ == "__main__":
    install_spacy_model()
