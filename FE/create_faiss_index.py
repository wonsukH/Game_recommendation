
import numpy as np
import faiss
import os

def create_faiss_index():
    """
    st_app/data/game_vecs.npy 파일을 읽어
    st_app/data/faiss_index.faiss 파일을 생성합니다.
    """
    data_folder = os.path.join("st_app", "data")
    game_vectors_path = os.path.join(data_folder, "game_vecs.npy")
    faiss_index_path = os.path.join(data_folder, "faiss_index.faiss")

    print(f"Loading game vectors from: {game_vectors_path}")
    
    if not os.path.exists(game_vectors_path):
        print(f"Error: {game_vectors_path} not found.")
        return

    try:
        game_vectors = np.load(game_vectors_path).astype('float32')
        d = game_vectors.shape[1]
        print(f"Vector dimension: {d}")
        print(f"Total vectors: {game_vectors.shape[0]}")

        # FAISS 인덱스 생성 (가장 기본적인 IndexFlatL2 사용)
        # IndexFlatL2는 모든 벡터와 거리를 직접 계산하여 가장 정확한 결과를 보장합니다.
        index = faiss.IndexFlatL2(d)
        print("Adding vectors to FAISS index...")
        index.add(game_vectors)
        print(f"Total vectors in index: {index.ntotal}")

        # 인덱스 파일로 저장
        print(f"Writing index to: {faiss_index_path}")
        faiss.write_index(index, faiss_index_path)

        print("\nSuccessfully created faiss_index.faiss!")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    create_faiss_index()
