from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class LoginFlow(StatesGroup):
    login = State()
    password = State()


class AddRuleFlow(StatesGroup):
    pick_slot = State()
    pick_mode = State()
