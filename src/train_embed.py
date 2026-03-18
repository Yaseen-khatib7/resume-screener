from typing import List
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer, InputExample, losses

def build_training_pairs_from_labels(
    jd_text: str,
    resume_texts: List[str],
    labels: List[int],
    pos_threshold: int = 2
) -> List[InputExample]:
    examples = []
    for rt, y in zip(resume_texts, labels):
        if y >= pos_threshold:
            examples.append(InputExample(texts=[jd_text, rt]))
    return examples

def finetune_sentence_transformer(
    base_model_name: str,
    train_examples: List[InputExample],
    output_dir: str,
    epochs: int = 1,
    batch_size: int = 16,
    warmup_steps: int = 50,
):
    model = SentenceTransformer(base_model_name)
    train_loader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)
    train_loss = losses.MultipleNegativesRankingLoss(model)

    model.fit(
        train_objectives=[(train_loader, train_loss)],
        epochs=epochs,
        warmup_steps=warmup_steps,
        show_progress_bar=True,
        output_path=output_dir
    )
    return output_dir