import torch
from torch import optim, nn
from torch.utils.data import DataLoader, random_split
from tqdm import tqdm

from unet import UNet
from underpass_dataset import UnderpassDataset

if __name__ == "__main__":

    LEARNING_RATE = 5e-5
    BATCH_SIZE = 16
    EPOCHS = 120
    DATA_PATH = r"u-net_model\data"
    MODEL_SAVE_PATH = r"u-net_model\model.pth"

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(device)
    train_dataset = UnderpassDataset(DATA_PATH)

    generator = torch.Generator().manual_seed(42)
    train_dataset, val_dataset = random_split(train_dataset, [0.8, 0.2], generator=generator)

    train_dataloader = DataLoader(dataset=train_dataset, batch_size=BATCH_SIZE, shuffle=True)

    val_dataloader = DataLoader(dataset=val_dataset, batch_size=BATCH_SIZE, shuffle=False)

    model = UNet(in_channels=3, num_classes=1).to(device)
    optimizer = optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    criterion = nn.BCEWithLogitsLoss()
    # criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([20.0]).to(device))

    best_val_loss = float("inf")

    for epoch in tqdm(range(EPOCHS)):
        model.train()
        train_running_loss = 0
        for idx, img_mask in enumerate(tqdm(train_dataloader)):
            img = img_mask[0].float().to(device)
            mask = img_mask[1].float().to(device)

            y_pred = model(img)
            optimizer.zero_grad()

            loss = criterion(y_pred, mask)
            train_running_loss += loss.item()

            loss.backward()
            optimizer.step()
        
        train_loss = train_loss = train_running_loss / (idx + 1)

        model.eval()
        val_running_loss = 0
        with torch.no_grad():
            for idx, img_mask in enumerate(tqdm(val_dataloader)):
                img = img_mask[0].float().to(device)
                mask = img_mask[1].float().to(device)

                y_pred = model(img)
                loss = criterion(y_pred, mask)

                val_running_loss += loss.item()

        val_loss = val_loss = val_running_loss / (idx + 1)

        print("-"*30)
        print(f"Train Loss EPOCH {epoch+1}: {train_loss:.4f}")
        print(f"Valid Loss EPOCH {epoch+1}: {val_loss:.4f}")
        
        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), MODEL_SAVE_PATH)
            print(f"Best model saved with val_loss: {val_loss:.4f}")
        
        print("-"*30)

# import torch
# from torch import optim, nn
# from torch.utils.data import DataLoader, random_split
# from tqdm import tqdm

# from unet import UNet
# from underpass_dataset import UnderpassDataset


# def dice_score(pred, target, eps=1e-7):
#     pred = torch.sigmoid(pred)
#     pred = (pred > 0.5).float()

#     intersection = (pred * target).sum()
#     union = pred.sum() + target.sum()

#     return (2 * intersection + eps) / (union + eps)


# def dice_loss(pred, target, eps=1e-7):
#     pred = torch.sigmoid(pred)

#     intersection = (pred * target).sum()
#     union = pred.sum() + target.sum()

#     dice = (2 * intersection + eps) / (union + eps)
#     return 1 - dice


# if __name__ == "__main__":

#     LEARNING_RATE = 5e-5
#     BATCH_SIZE = 8
#     EPOCHS = 120
#     DATA_PATH = r"D:\internship\u-net_model\data"
#     MODEL_SAVE_PATH = r"D:\internship\u-net_model\model.pth"

#     device = "cuda" if torch.cuda.is_available() else "cpu"

#     dataset = UnderpassDataset(DATA_PATH)

#     generator = torch.Generator().manual_seed(42)
#     train_dataset, val_dataset = random_split(dataset, [0.8, 0.2], generator=generator)

#     train_dataloader = DataLoader(
#         dataset=train_dataset,
#         batch_size=BATCH_SIZE,
#         shuffle=True,
#         num_workers=2,
#         pin_memory=True
#     )

#     val_dataloader = DataLoader(
#         dataset=val_dataset,
#         batch_size=BATCH_SIZE,
#         shuffle=False
#     )

#     model = UNet(in_channels=3, num_classes=1).to(device)

#     optimizer = optim.AdamW(model.parameters(), lr=LEARNING_RATE)

#     scheduler = optim.lr_scheduler.ReduceLROnPlateau(
#         optimizer,
#         mode="min",
#         factor=0.5,
#         patience=5,
#         verbose=True
#     )

#     bce_loss = nn.BCEWithLogitsLoss()

#     best_val_loss = float("inf")

#     for epoch in range(EPOCHS):

#         # ---------------- TRAIN ----------------
#         model.train()
#         train_running_loss = 0

#         train_loop = tqdm(train_dataloader)

#         for img, mask in train_loop:

#             img = img.float().to(device)
#             mask = mask.float().to(device)

#             optimizer.zero_grad()

#             y_pred = model(img)

#             loss = bce_loss(y_pred, mask) + dice_loss(y_pred, mask)

#             loss.backward()
#             optimizer.step()

#             train_running_loss += loss.item()

#         train_loss = train_running_loss / len(train_dataloader)

#         # ---------------- VALIDATION ----------------
#         model.eval()
#         val_running_loss = 0
#         val_dice = 0

#         with torch.no_grad():

#             for img, mask in val_dataloader:

#                 img = img.float().to(device)
#                 mask = mask.float().to(device)

#                 y_pred = model(img)

#                 loss = bce_loss(y_pred, mask) + dice_loss(y_pred, mask)

#                 val_running_loss += loss.item()
#                 val_dice += dice_score(y_pred, mask).item()

#         val_loss = val_running_loss / len(val_dataloader)
#         val_dice = val_dice / len(val_dataloader)

#         scheduler.step(val_loss)

#         # Save best model
#         if val_loss < best_val_loss:
#             best_val_loss = val_loss
#             torch.save(model.state_dict(), MODEL_SAVE_PATH)

#         print("-" * 40)
#         print(f"EPOCH {epoch+1}/{EPOCHS}")
#         print(f"Train Loss: {train_loss:.4f}")
#         print(f"Valid Loss: {val_loss:.4f}")
#         print(f"Valid Dice: {val_dice:.4f}")
#         print("-" * 40)