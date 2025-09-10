# Copyright 2025 Alun King
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

# Configure logging level and format
logging.basicConfig(
    level=logging.INFO,  # options: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()  # prints to console
    ]
)

from sklearn.preprocessing import normalize
from backend.config import settings
from sqlalchemy.orm import Session
from datetime import datetime
import torch
from pyannote.audio import Model, Inference
import os
from backend.processing.device_management import get_safe_device, safe_run_model

# Get Hugging Face token stored in env file
HUGGING_FACE_TOKEN = os.getenv("HUGGING_FACE_TOKEN")
if not HUGGING_FACE_TOKEN:
    raise RuntimeError("HUGGING_FACE_TOKEN environment variable not set.")

def generate_embedding(member_id: int, db: Session):
    logging.info(f"Started embedding process for member_id={member_id}")
    from backend.models import GroupMember

    #load speaker samples and generate the embeddings to be tested below
    logging.debug("Loading pyannote/embedding model")
    embedding_model = Model.from_pretrained("pyannote/embedding",
                              use_auth_token=HUGGING_FACE_TOKEN)
    

    # Ask device manager what’s safe
    device, msg = get_safe_device()
    logging.info(msg)

    # Move the model safely
    embedding_model.to(torch.device(device))

    embedding_inference = Inference(embedding_model, window="whole")

    try:
        logging.debug(f"Getting member information")
        member = db.query(GroupMember).get(member_id)
        if not member:
            logging.warning(f"Member with id={member_id} not found during embedding update.")
            return  # Or log
        
        # Define path
        embedding_dir = settings.EMBEDDING_DIR
        audio_path = embedding_dir / member.embedding_audio_path

        #check file exists before processing
        if audio_path.exists():
            logging.info(f"Running inference on file: {audio_path}")

            #use this definition to pass the call to safe_run_model
            def run_inference(path, inference_obj):
                return inference_obj(path)

            embedding_vector = safe_run_model(run_inference, audio_path, inference_obj=embedding_inference)

            embedding_array = embedding_vector.reshape(1, -1)  # (1, 512)
            embedding_array = normalize(embedding_array)       # L2 normalize
            embedding_list = embedding_array.flatten().tolist()
        

            member.embedding = embedding_list
            member.embedding_updated_at = datetime.now().astimezone()
            db.commit()

            logging.info(f"Embedding complete for member {member_id}, and database updated.")
        else:
            logging.warning(f"No audio file found at {audio_path} for member_id={member_id}")
            return
    except Exception as e:
        # You might want logging here
        logging.error(f"Embedding failed for member_id={member_id}: {e}", exc_info=True)
