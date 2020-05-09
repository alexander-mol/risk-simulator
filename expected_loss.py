from main import dice_battle

n_trials = 1000000

att_strength = 100000


def stack_battle(att_strength, def_strenth):
    total_att_loss, total_def_loss = 0, 0
    while att_strength >= 4 and def_strenth > 0:
        att_loss, def_loss = dice_battle(min(3, att_strength - 1), min(2, def_strenth))
        att_strength -= att_loss
        def_strenth -= def_loss
        total_att_loss += att_loss
        total_def_loss += def_loss
    return total_att_loss, total_def_loss


print(f"def_strength,exp_loss")
for def_strength in range(1, 20):
    total_loss = 0
    for _ in range(n_trials):
        att_loss, def_loss = stack_battle(att_strength, def_strength)
        total_loss += att_loss
    expected_loss = total_loss / n_trials
    print(f"{def_strength},{expected_loss:.3f}")

