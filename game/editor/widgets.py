"""Small drawing helpers shared by the map editor's full-screen panels (Monsters, Quests & NPCs)."""
import pygame

BG, PANEL, LINE, TEXT, DIM, GOLD, RED, GREEN = ((25, 25, 30), (45, 45, 52), (90, 90, 100), (225, 225, 225),
                                               (140, 140, 150), (255, 210, 90), (255, 110, 110), (120, 220, 130))


class Widgets:
    """Mixin: clickable buttons / value boxes that record their rectangles in self.hits (and a hover help line in
    self.help); click() looks the rectangle up and calls _do_<action>(arg, button)."""
    hits = ()
    help = ""

    def _hit(self, rect, action, arg=None):
        self.hits.append((pygame.Rect(rect), action, arg))

    def _button(self, surf, font, rect, label, action, arg=None, color=(70, 70, 82), text=TEXT):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surf, tuple(min(255, c + 20) for c in color) if hover else color, rect, border_radius=4)
        pygame.draw.rect(surf, LINE, rect, 1, border_radius=4)
        t = font.render(label, True, text)
        surf.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
        self._hit(rect, action, arg)

    def _box(self, surf, font, rect, text, action, arg, active=False, help_text=""):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(pygame.mouse.get_pos())
        if hover and help_text:
            self.help = help_text
        pygame.draw.rect(surf, (60, 95, 60) if active else ((66, 66, 78) if hover else (52, 52, 62)), rect,
                         border_radius=4)
        pygame.draw.rect(surf, LINE, rect, 1, border_radius=4)
        surf.blit(font.render(str(text), True, TEXT), (rect.x + 6, rect.y + 5))
        self._hit(rect, action, arg)

