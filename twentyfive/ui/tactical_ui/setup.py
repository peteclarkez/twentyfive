"""
Setup lobby — called by __main__.py before the game engine is created.
"""

from __future__ import annotations

import pygame

from .constants import (
    _BG_CARD,
    _BG_DARK,
    _BG_PANEL,
    _CYAN,
    _DANGER,
    _DIVIDER,
    _EMERALD,
    _EMERALD_D,
    _GOLD,
    _H,
    _PANEL_BDR,
    _SETUP_AI_TYPES,
    _SETUP_NAMES,
    _TEXT_MUT,
    _TEXT_PRI,
    _W,
)
from .widgets import _blend


def setup_game() -> tuple[list[str], dict[str, str]] | None:
    """
    Show a pygame setup lobby.

    Returns ``(player_names, {name: type_string})`` where *type_string* is one
    of "Human", "Random", "Heuristic", "Enhanced", "ISMCTS".
    Returns ``None`` if the user closes the window without starting.
    """
    pygame.init()
    screen = pygame.display.set_mode((_W, _H))
    pygame.display.set_caption("Twenty-Five — Setup")
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont("monospace", 40, bold=True)
    font_hdr = pygame.font.SysFont("monospace", 22, bold=True)
    font_md = pygame.font.SysFont("monospace", 20)
    font_sm = pygame.font.SysFont("monospace", 16)

    # --- State ---
    n = 4
    names: list[str] = list(_SETUP_NAMES[:6])  # always keep 6 slots; use names[:n]
    ai_types: list[str] = ["Enhanced"] * 6
    focused = -1  # index of name field being edited, or -1

    # --- Layout ---
    TBL_X = 180
    NUM_COL_W = 50
    NAME_COL_X = TBL_X + NUM_COL_W
    NAME_COL_W = 360
    TYPE_COL_X = NAME_COL_X + NAME_COL_W + 20
    TYPE_COL_W = 300
    ROW_H = 52
    ROWS_Y = 285
    HDR_Y = ROWS_Y - 34
    COUNT_Y = 158
    COUNT_X0 = _W // 2 - (5 * 70) // 2

    BTN_Y = ROWS_Y + 6 * ROW_H + 24
    start_rect = pygame.Rect(_W // 2 - 130, BTN_Y, 230, 46)
    quit_rect = pygame.Rect(_W // 2 + 115, BTN_Y, 110, 46)

    def _count_rect(n_val: int) -> pygame.Rect:
        return pygame.Rect(COUNT_X0 + (n_val - 2) * 70, COUNT_Y, 60, 36)

    def _name_rect(i: int) -> pygame.Rect:
        return pygame.Rect(NAME_COL_X, ROWS_Y + i * ROW_H + 10, NAME_COL_W, 32)

    def _type_prev_rect(i: int) -> pygame.Rect:
        return pygame.Rect(TYPE_COL_X, ROWS_Y + i * ROW_H + 10, 30, 32)

    def _type_next_rect(i: int) -> pygame.Rect:
        return pygame.Rect(TYPE_COL_X + TYPE_COL_W - 30, ROWS_Y + i * ROW_H + 10, 30, 32)

    t_start = pygame.time.get_ticks() / 1000.0
    running = True
    result: tuple[list[str], dict[str, str]] | None = None

    while running:
        t = pygame.time.get_ticks() / 1000.0 - t_start
        mouse = pygame.mouse.get_pos()
        screen.fill(_BG_DARK)

        # Title
        title_s = font_title.render("TWENTY-FIVE", True, _GOLD)
        screen.blit(title_s, title_s.get_rect(centerx=_W // 2, y=38))
        sub_s = font_hdr.render("Player Setup", True, _TEXT_MUT)
        screen.blit(sub_s, sub_s.get_rect(centerx=_W // 2, y=86))
        pygame.draw.line(screen, _DIVIDER, (80, 120), (_W - 80, 120), 1)

        # Player count selector
        lbl_s = font_md.render("Number of Players:", True, _TEXT_PRI)
        screen.blit(lbl_s, lbl_s.get_rect(centerx=_W // 2, y=130))
        for n_val in range(2, 7):
            r = _count_rect(n_val)
            sel = n_val == n
            pygame.draw.rect(screen, _EMERALD_D if sel else _BG_PANEL, r, border_radius=6)
            pygame.draw.rect(screen, _EMERALD if sel else _PANEL_BDR, r, 1, border_radius=6)
            cs = font_hdr.render(str(n_val), True, _EMERALD if sel else _TEXT_PRI)
            screen.blit(cs, cs.get_rect(center=r.center))

        # Column headers
        pygame.draw.line(
            screen, _DIVIDER, (TBL_X, HDR_Y + 26), (TYPE_COL_X + TYPE_COL_W, HDR_Y + 26), 1
        )
        screen.blit(font_hdr.render("#", True, _TEXT_MUT), (TBL_X + 12, HDR_Y))
        screen.blit(font_hdr.render("Name", True, _TEXT_MUT), (NAME_COL_X + 4, HDR_Y))
        screen.blit(font_hdr.render("Type", True, _TEXT_MUT), (TYPE_COL_X + 4, HDR_Y))

        # Player rows
        for i in range(6):
            active_row = i < n
            row_y = ROWS_Y + i * ROW_H

            if not active_row:
                dim = font_sm.render(f"— slot {i + 1} inactive —", True, _DIVIDER)
                screen.blit(dim, dim.get_rect(x=NAME_COL_X, y=row_y + 16))
                continue

            # Row number
            num_s = font_md.render(str(i + 1), True, _GOLD if i == 0 else _TEXT_MUT)
            screen.blit(num_s, num_s.get_rect(centerx=TBL_X + NUM_COL_W // 2, y=row_y + 18))

            # Name input field
            nr = _name_rect(i)
            is_focused = i == focused
            pygame.draw.rect(screen, _BG_CARD if is_focused else _BG_PANEL, nr, border_radius=4)
            pygame.draw.rect(screen, _CYAN if is_focused else _PANEL_BDR, nr, 1, border_radius=4)
            cursor = "|" if is_focused and int(t * 2) % 2 == 0 else ""
            nm_s = font_md.render(names[i] + cursor, True, _TEXT_PRI)
            screen.blit(nm_s, (nr.x + 6, nr.y + 6))

            # Type selector: [<]  TypeLabel  [>]
            pv = _type_prev_rect(i)
            nx = _type_next_rect(i)
            type_label_x = pv.right + 4
            type_label_w = nx.left - pv.right - 8

            for btn_r, lbl in [(pv, "<"), (nx, ">")]:
                hov = btn_r.collidepoint(mouse)
                pygame.draw.rect(
                    screen,
                    _blend(_BG_PANEL, _TEXT_PRI, 0.15) if hov else _BG_PANEL,
                    btn_r,
                    border_radius=4,
                )
                pygame.draw.rect(screen, _PANEL_BDR, btn_r, 1, border_radius=4)
                ls = font_md.render(lbl, True, _TEXT_PRI)
                screen.blit(ls, ls.get_rect(center=btn_r.center))

            type_str = ai_types[i]
            type_col = _EMERALD if type_str == "Human" else _GOLD
            ts = font_md.render(type_str, True, type_col)
            screen.blit(ts, ts.get_rect(center=(type_label_x + type_label_w // 2, pv.centery)))

        # Divider before buttons
        div_y = ROWS_Y + 6 * ROW_H + 10
        pygame.draw.line(screen, _DIVIDER, (80, div_y), (_W - 80, div_y), 1)

        # Start / Quit buttons
        for r, lbl, col, bdr_col in [
            (start_rect, "START GAME", _EMERALD_D, _EMERALD),
            (quit_rect, "QUIT", _BG_PANEL, _DANGER),
        ]:
            hov = r.collidepoint(mouse)
            pygame.draw.rect(
                screen, _blend(col, _TEXT_PRI, 0.15) if hov else col, r, border_radius=8
            )
            pygame.draw.rect(screen, bdr_col, r, 1, border_radius=8)
            ls = font_hdr.render(lbl, True, _TEXT_PRI)
            screen.blit(ls, ls.get_rect(center=r.center))

        # Hint
        hint = font_sm.render(
            "Click a name to edit  ·  < > to change type  ·  ESC to quit", True, _TEXT_MUT
        )
        screen.blit(hint, hint.get_rect(centerx=_W // 2, y=BTN_Y + 56))

        # --- Events ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif focused >= 0:
                    if event.key == pygame.K_BACKSPACE:
                        names[focused] = names[focused][:-1]
                    elif event.key in (pygame.K_RETURN, pygame.K_TAB):
                        focused = (focused + 1) % n
                    elif event.unicode.isprintable() and len(names[focused]) < 18:
                        names[focused] += event.unicode

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos

                # Player count buttons
                for n_val in range(2, 7):
                    if _count_rect(n_val).collidepoint(pos):
                        n = n_val
                        focused = -1
                        break

                # Name fields — clicking sets focus; clicking elsewhere clears it
                new_focus = -1
                for i in range(n):
                    if _name_rect(i).collidepoint(pos):
                        new_focus = i
                        break
                focused = new_focus

                # Type < / > buttons
                for i in range(n):
                    if _type_prev_rect(i).collidepoint(pos):
                        idx = _SETUP_AI_TYPES.index(ai_types[i])
                        ai_types[i] = _SETUP_AI_TYPES[(idx - 1) % len(_SETUP_AI_TYPES)]
                    elif _type_next_rect(i).collidepoint(pos):
                        idx = _SETUP_AI_TYPES.index(ai_types[i])
                        ai_types[i] = _SETUP_AI_TYPES[(idx + 1) % len(_SETUP_AI_TYPES)]

                # Start / Quit
                if start_rect.collidepoint(pos):
                    final_names = [nm.strip() or _SETUP_NAMES[i] for i, nm in enumerate(names[:n])]
                    type_map = {final_names[i]: ai_types[i] for i in range(n)}
                    result = (final_names, type_map)
                    running = False
                elif quit_rect.collidepoint(pos):
                    running = False

        pygame.display.flip()
        clock.tick(60)

    return result
