import os
import pandas as pd

base_path = "/Users/victormilani/train_ia_stag"
csv_path = os.path.join(base_path, "/Users/victormilani/train_ia_stag/Data/dados_treino_adb/dataset.csv")
frames_dir = os.path.join(base_path, "/Users/victormilani/train_ia_stag/Data/dados_treino_adb/frames")

df = pd.read_csv(csv_path)

# Corrige e verifica se a imagem existe
def get_valid_path(img_path):
    filename = os.path.basename(img_path)
    full_path = os.path.join(frames_dir, filename)
    return full_path if os.path.exists(full_path) else None

df["corrected_path"] = df.iloc[:, 0].apply(get_valid_path)
df = df.dropna(subset=["corrected_path"])
df.iloc[:, 0] = df["corrected_path"]
df = df.drop(columns=["corrected_path"])
df.to_csv(csv_path, index=False)

print(f"✅ Dataset filtrado com sucesso. Total de imagens válidas: {len(df)}")