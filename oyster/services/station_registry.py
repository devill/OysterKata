from __future__ import annotations


class StationRegistry:
    _ZONES: dict[str, tuple[int, ...]] = {
        "Oxford Circus": (1,),
        "King's Cross": (1,),
        "Waterloo": (1,),
        "Victoria": (1,),
        "Liverpool Street": (1,),
        "Camden Town": (2,),
        "Brixton": (2,),
        "Hackney Central": (2,),
        "Finsbury Park": (2,),
        "Stratford": (2, 3),
        "Wembley Central": (3, 4),
        "Ealing Broadway": (3,),
        "Lewisham": (3,),
        "Wood Green": (3,),
        "Walthamstow Central": (3,),
        "Hounslow Central": (4,),
        "Harrow-on-the-Hill": (4,),
        "Cockfosters": (5,),
        "Hayes & Harlington": (5,),
        "Uxbridge": (6,),
        "Epping": (6,),
    }

    def zones_for(self, station: str) -> tuple[int, ...]:
        try:
            return self._ZONES[station]
        except KeyError:
            raise KeyError(f"Unknown station: {station!r}") from None
