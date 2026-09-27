"""Known provider names in Portuguese; unknown names remain unchanged."""
from backend.comparison import normalized_name

NAMES = {
    'brazil': 'Brasil', 'italy': 'Itália', 'belgium': 'Bélgica', 'latvia': 'Letônia',
    'armenia': 'Armênia', 'germany': 'Alemanha', 'spain': 'Espanha', 'france': 'França',
    'england': 'Inglaterra', 'scotland': 'Escócia', 'wales': 'País de Gales',
    'northern ireland': 'Irlanda do Norte', 'republic of ireland': 'Irlanda', 'ireland': 'Irlanda',
    'netherlands': 'Holanda', 'the netherlands': 'Holanda', 'croatia': 'Croácia',
    'denmark': 'Dinamarca', 'sweden': 'Suécia', 'norway': 'Noruega', 'finland': 'Finlândia',
    'switzerland': 'Suíça', 'austria': 'Áustria', 'poland': 'Polônia', 'ukraine': 'Ucrânia',
    'czechia': 'República Tcheca', 'czech republic': 'República Tcheca', 'slovakia': 'Eslováquia',
    'slovenia': 'Eslovênia', 'serbia': 'Sérvia', 'hungary': 'Hungria', 'romania': 'Romênia',
    'greece': 'Grécia', 'turkey': 'Turquia', 'turkiye': 'Turquia', 'iceland': 'Islândia',
    'estonia': 'Estônia', 'lithuania': 'Lituânia', 'georgia': 'Geórgia', 'albania': 'Albânia',
    'bosnia and herzegovina': 'Bósnia e Herzegovina', 'north macedonia': 'Macedônia do Norte',
    'bulgaria': 'Bulgária', 'moldova': 'Moldávia', 'cyprus': 'Chipre', 'azerbaijan': 'Azerbaijão',
    'faroe islands': 'Ilhas Faroe', 'belarus': 'Belarus', 'russia': 'Rússia',
    'united states': 'Estados Unidos', 'usa': 'Estados Unidos', 'mexico': 'México',
    'canada': 'Canadá', 'japan': 'Japão', 'south korea': 'Coreia do Sul',
    'korea republic': 'Coreia do Sul', 'china': 'China', 'saudi arabia': 'Arábia Saudita',
    'iran': 'Irã', 'iraq': 'Iraque', 'australia': 'Austrália', 'new zealand': 'Nova Zelândia',
    'morocco': 'Marrocos', 'egypt': 'Egito', 'algeria': 'Argélia', 'tunisia': 'Tunísia',
    'ivory coast': 'Costa do Marfim', 'cote d ivoire': 'Costa do Marfim',
    'south africa': 'África do Sul', 'cameroon': 'Camarões', 'nigeria': 'Nigéria',
    'uruguay': 'Uruguai', 'paraguay': 'Paraguai', 'ecuador': 'Equador', 'colombia': 'Colômbia',
    'bolivia': 'Bolívia', 'bayern munich': 'Bayern de Munique', 'internazionale': 'Inter de Milão',
    'inter milan': 'Inter de Milão', 'ac milan': 'Milan', 'as roma': 'Roma',
    'sporting cp': 'Sporting', 'atletico madrid': 'Atlético de Madrid',
}

def display_name(value):
    return NAMES.get(normalized_name(value or ''), value)

def canonical_name(value):
    return normalized_name(display_name(value) or '')
