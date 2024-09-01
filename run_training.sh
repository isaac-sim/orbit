MODE=$1
NUM_ENVS=15 #32
VIDEO_LEN=200
VIDEO_INTERVAL=500
PATH_TO_CHECKPOINT="./logs/skrl/franka_lift/2024-08-06_22-22-33/checkpoints/best_agent.pt"

if [ $MODE = "train_rgb_and_state" ]; then
    echo "Training"
    python source/standalone/workflows/skrl/train_rgb.py \
    --task Isaac-Lift-Cube-Franka-v0-RGB \
    --num_envs $NUM_ENVS \
    --arch_type large_model-rgb-state \
    --headless \
    --enable_cameras \
    --video --video_length $VIDEO_LEN --video_interval $VIDEO_INTERVAL \
    #--wandb \
    #--checkpoint /PATH/TO/model.pt

elif [ $MODE = "train_state" ]; then
    python source/standalone/workflows/skrl/train.py \
    --task Isaac-Lift-Cube-Franka-v0 \
    --num_envs $NUM_ENVS \
    --headless \
    --enable_cameras \
    --video --video_length $VIDEO_LEN --video_interval $VIDEO_INTERVAL #\
    #--wandb \
    #--checkpoint /PATH/TO/model.pt

else
    echo "Playing"
    python source/standalone/workflows/skrl/play_rgb.py --task Isaac-Lift-Cube-Franka-v0-RGB --num_envs 2 \
    --headless \
    --enable_cameras
fi