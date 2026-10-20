"""Teaching RSA-FDH blind signatures and salted XOR identity commitments."""
import hashlib
import json
import math
import secrets
from cryptography.hazmat.primitives.asymmetric import rsa

class ProtocolError(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise ProtocolError(message)

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True)

def token():
    return secrets.token_hex(32)

def hx(value, size=32):
    require(isinstance(value, str) and len(value) == size * 2, '十六进制字段长度错误')
    try:
        b = bytes.fromhex(value)
    except ValueError as e:
        raise ProtocolError('非法十六进制字段') from e
    require(len(b) == size and b.hex() == value, '十六进制字段必须为规范小写')
    return b

def xor(a, b):
    require(len(a) == len(b), 'XOR 长度错误')
    return bytes(x ^ y for x, y in zip(a, b))

def integer(value, low, high):
    require(type(value) is int and low <= value <= high, '整数超出允许范围')
    return value

def generate_key():
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_numbers()
    pub = {'n': str(k.public_numbers.n), 'e': k.public_numbers.e, 'version': 1,
           'amount': 10}
    pub['key_id'] = hashlib.sha256(canonical(pub).encode()).hexdigest()
    return pub, str(k.d)

def unit(n):
    while True:
        r = secrets.randbelow(n - 3) + 2
        if math.gcd(r, n) == 1:
            return r

def representative(coin, public):
    n = int(public['n'])
    # Domain-separated full-domain rejection sampling (teaching construction, not RFC 9474).
    seed = ('OFFLINE-CASH-FDH-v1|' + canonical(coin)).encode()
    size = (n.bit_length() + 7) // 8
    counter = 0
    while True:
        m = int.from_bytes(hashlib.shake_256(seed + counter.to_bytes(4, 'big')).digest(size), 'big')
        if 1 < m < n and math.gcd(m, n) == 1:
            return m
        counter += 1

def commitment(serial, i, side, share, salt):
    return hashlib.sha256(canonical(['OFFLINE-CASH-SHARE-v1', serial, i, side, share, salt]).encode()).hexdigest()

def validate_coin(coin, public):
    require(isinstance(coin, dict) and set(coin) == {'version','key_id','amount','serial','t','commitments'}, '货币结构错误')
    require(type(coin['version']) is int and coin['version'] == 1 and coin['key_id'] == public['key_id'], '版本或发行密钥不匹配')
    require(type(coin['amount']) is int and coin['amount'] == public['amount'], '只支持固定面额 10')
    hx(coin['serial'])
    t = integer(coin['t'], 8, 128)
    require(isinstance(coin['commitments'], list) and len(coin['commitments']) == t, '承诺数量错误')
    for pair in coin['commitments']:
        require(isinstance(pair, list) and len(pair) == 2, '承诺对错误')
        for c in pair:
            hx(c)

def candidate(identity, public, t=32):
    u = hx(identity)
    integer(t, 8, 128)
    serial = token()
    pairs, opening = [], []
    for i in range(t):
        left = secrets.token_bytes(32)
        right = xor(left, u)
        sides = [{'share': x.hex(), 'salt': token()} for x in (left, right)]
        opening.append(sides)
        pairs.append([commitment(serial, i, s, **sides[s]) for s in (0, 1)])
    coin = dict(version=1, key_id=public['key_id'], amount=10, serial=serial, t=t, commitments=pairs)
    n = int(public['n'])
    r = unit(n)
    blinded = representative(coin, public) * pow(r, public['e'], n) % n
    return {'coin':coin, 'opening':opening, 'r':str(r), 'blinded':str(blinded)}

def scalar(value, public):
    require(isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 620, 'RSA 标量格式错误')
    require(value == str(int(value)), 'RSA 标量必须规范编码')
    n = int(public['n'])
    v = int(value)
    require(1 < v < n and math.gcd(v, n) == 1, 'RSA 标量不在可逆群中')
    return v

def check_opening(c, identity, blinded, public):
    require(isinstance(c, dict) and set(c) == {'coin','opening','r','blinded'}, '开封结构错误')
    coin = c['coin']
    validate_coin(coin, public)
    require(isinstance(c['opening'], list) and len(c['opening']) == coin['t'], '开封数量错误')
    for i, pair in enumerate(c['opening']):
        require(isinstance(pair, list) and len(pair) == 2, '开封分支错误')
        for side, item in enumerate(pair):
            require(isinstance(item, dict) and set(item) == {'share','salt'}, '开封字段错误')
            hx(item['share']); hx(item['salt'])
            require(commitment(coin['serial'], i, side, **item) == coin['commitments'][i][side], '承诺不匹配')
        require(xor(hx(pair[0]['share']), hx(pair[1]['share'])).hex() == identity, '候选身份不属于取款账户')
    r = scalar(c['r'], public)
    expected = representative(coin, public) * pow(r, public['e'], int(public['n'])) % int(public['n'])
    require(c['blinded'] == blinded and str(expected) == blinded, '盲化值与已提交数据不符')

def unblind(c, blind_signature, public):
    n = int(public['n'])
    signature = str(scalar(blind_signature, public) * pow(scalar(c['r'], public), -1, n) % n)
    cash = {'coin':c['coin'], 'signature':signature}
    verify_cash(cash, public)
    return cash

def verify_cash(cash, public):
    require(isinstance(cash, dict) and set(cash) == {'coin','signature'}, '电子现金字段错误')
    validate_coin(cash['coin'], public)
    sig = scalar(cash['signature'], public)
    require(pow(sig, public['e'], int(public['n'])) == representative(cash['coin'], public), '银行签名无效')

def verify_transcript(tr, public):
    require(isinstance(tr, dict) and set(tr) == {'payment_id','merchant','cash','challenge','responses'}, '支付凭证结构错误')
    hx(tr['payment_id'])
    require(isinstance(tr['merchant'], str) and 1 <= len(tr['merchant']) <= 40, '商户标识错误')
    verify_cash(tr['cash'], public)
    coin = tr['cash']['coin']
    bits = tr['challenge']
    require(isinstance(bits, list) and len(bits) == coin['t'], '挑战长度错误')
    require(isinstance(tr['responses'], list) and len(tr['responses']) == coin['t'], '响应长度错误')
    for i, (b, item) in enumerate(zip(bits, tr['responses'])):
        integer(b, 0, 1)
        require(isinstance(item, dict) and set(item) == {'share','salt'}, '响应字段错误')
        hx(item['share']); hx(item['salt'])
        require(commitment(coin['serial'], i, b, **item) == coin['commitments'][i][b], '挑战响应不匹配')

def recover(first, second, public):
    verify_transcript(first, public); verify_transcript(second, public)
    require(first['cash'] == second['cash'], '不是同一枚电子现金')
    identities = set()
    positions = []
    for i, (a, b) in enumerate(zip(first['challenge'], second['challenge'])):
        if a != b:
            identities.add(xor(hx(first['responses'][i]['share']), hx(second['responses'][i]['share'])).hex())
            positions.append(i)
    require(len(identities) <= 1, '不同位置恢复身份不一致：候选结构可能作弊')
    return (next(iter(identities)) if identities else None), positions
