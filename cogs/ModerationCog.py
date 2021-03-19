import re
import json
import discord
from discord.ext import commands
from datetime import datetime, timedelta
from cogs import sharedFunctions

"""contiene i comandi relativi alla moderazione, in particolare:
- warn
- unwarn
- ban
- warncount
Inoltre effettua il controllo sul contenuto dei messaggi e elimina quelli dal contenuto inadatto
"""

class ModerationCog(commands.Cog):
    def __init__(self, bot, config):
        self.bot = bot
        self.GUILD_ID = int(config['guild_id'])
        self.MODERATION_ROLES_ID = []
        for mod in config['moderation_roles_id']:
            self.MODERATION_ROLES_ID.append(int(mod))
        self.EXCEPTIONAL_CHANNELS_ID = []
        for channel in config['exceptional_channels_id']:
            self.EXCEPTIONAL_CHANNELS_ID.append(int(channel))
        self.UNDER_SURVEILLANCE_ID = int(config['under_surveillance_id'])

    async def cog_check(self, ctx):
        """check sui comandi per bloccare l'utilizzo dei comandi di moderazione"""
        return ctx.author.top_role.id in self.MODERATION_ROLES_ID

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user or message.author.bot or message.guild is None:
            return
        if sharedFunctions.BannedWords.contains_banned_words(message.content) and message.channel.id not in self.EXCEPTIONAL_CHANNELS_ID:
            await message.delete()
            await ModerationCog._add_warn(message.author, 'linguaggio inappropriato', 1, self.bot, self.GUILD_ID, self.UNDER_SURVEILLANCE_ID)

    @commands.command()
    async def warn(self, ctx, attempted_member=None, *, reason='un moderatore ha ritenuto inopportuno il tuo comportamento'):
        """aggiunge un warn all'utente menzionato nel messaggio (basta il nome)
        L'effetto è il seguente:
        - aggiunge un warn all'autore del messaggio a cui si risponde/utente menzionato
        - cancella il messaggio citato (se presente)
        - cancella il comando di warn
        """
        if attempted_member is None:   #nessun argomento passato al warn
            if ctx.message.reference is None:
                #sono in questo caso quando mando <warn da solo
                await ctx.send("Devi menzionare qualcuno o rispondere a un messaggio per poter usare questo comando", delete_after=5)
                return
            else:
                #in questo caso ho risposto a un messaggio con <warn
                msg = await ctx.fetch_message(ctx.message.reference.message_id)
                member = msg.author
                await msg.delete()
        else:   #con argomenti al warn
            if not ctx.message.mentions:   #nessuna menzione nel messaggio
                await ctx.send("Devi menzionare qualcuno o rispondere a un messaggio per poter usare questo comando", delete_after=5)
                return
            else:
                if ctx.message.reference is None:
                    #ho chiamato il warn a mano <warn @somebody ragione
                    member = ctx.message.mentions[0]
                else:
                    #ho menzionato qualcuno, prendo come target del warn
                    msg = await ctx.fetch_message(ctx.message.reference.message_id)
                    member = msg.author
                    await msg.delete()
                    #solo se vado per reference devo sistemare la reason perchè la prima parola va in attempted_member
                    if reason == 'un moderatore ha ritenuto inopportuno il tuo comportamento':
                        reason = attempted_member   #ragione di una sola parola, altrimenti poi concatena tutto
                    else:
                        reason = attempted_member + ' ' + reason  #devo inserire uno spazio altrimenti scrive tutto appicciato
        if member.bot:   # or member == ctx.author:
            return
        await ModerationCog._add_warn(member, reason, 1, self.bot, self.GUILD_ID, self.UNDER_SURVEILLANCE_ID)
        user = '<@!' + str(member.id) + '>'
        await ctx.send(user + ' warnato. Motivo: ' + reason)
        await ctx.message.delete(delay=5)   

    @commands.command()
    async def unwarn(self, ctx, member: discord.Member):
        """rimuove un warn all'utente menzionato"""
        if member.bot:
            return
        reason = 'buona condotta'
        await ModerationCog._add_warn(member, reason, -1, self.bot, self.GUILD_ID, self.UNDER_SURVEILLANCE_ID)
        user = '<@!' + str(member.id) + '>'
        await ctx.send(user + ' rimosso un warn.')
        await ctx.message.delete(delay=5)

    @commands.command(aliases=['warnc', 'wc'])
    async def warncount(self, ctx):
        """stampa nel canale in cui viene chiamato l'elenco di tutti i warn degli utenti."""
        try:
            with open('aflers.json','r') as file:
                prev_dict = json.load(file)
        except FileNotFoundError:
            await ctx.send('nessuna attività registrata', delete_after=5)
            await ctx.message.delete(delay=5)
            return
        warnc = ''
        for user in prev_dict:
            name = self.bot.get_guild(self.GUILD_ID).get_member(int(user)).display_name
            item = prev_dict[user]
            count = str(item["violations_count"])
            msg = name + ': ' + count + ' warn\n'
            warnc += msg
        await ctx.send(warnc)

    @commands.command()
    async def ban(self, ctx, member: discord.Member = None, *, reason='un moderatore ha ritenuto inopportuno il tuo comportamento'):
        """banna un membro dal server"""
        if member is None:
            await ctx.send('specifica un membro da bannare', delete_after=5)
            await ctx.message.delete(delay=5)
            return
        user = '<@!' + str(member.id) + '>'
        await ctx.send(user + ' bannato. Motivo: ' + reason)
        await ctx.message.delete(delay=5)
        penalty = 'bannato dal server.' 
        channel = await member.create_dm()
        await channel.send('Sei stato ' + penalty + ' Motivo: ' + reason + '.')
        await member.ban(delete_message_days = 0, reason = reason)

    async def _add_warn(member, reason, number, bot, GUILD_ID, UNDER_SURVEILLANCE_ID):
        """incrementa o decremente il numero di violazioni di numero e tiene traccia dell'ultima violazione commessa"""
        prev_dict = {}
        penalty = 'warnato.'
        try:
            with open('aflers.json','r') as file:
                prev_dict = json.load(file)
        except FileNotFoundError:
            print('file non trovato, lo creo ora')
            with open('aflers.json','w+') as file:
                prev_dict = {}
        finally:
            key = str(member.id)
            if key in prev_dict:
                d = prev_dict[key]
                d["violations_count"] += number
                d["last_violation_count"] = datetime.date(datetime.now()).__str__()
                sharedFunctions.update_json_file(prev_dict, 'aflers.json')
                if d["violations_count"] <= 0:
                    d["violations_count"] = 0
                    d["last_violation_count"] = None
                    sharedFunctions.update_json_file(prev_dict, 'aflers.json')
                    return
                if number < 0:  #non deve controllare se è un unwarn
                    return
                if d["violations_count"] == 3:
                    await member.add_roles(bot.get_guild(GUILD_ID).get_role(UNDER_SURVEILLANCE_ID))
                    penalty = 'sottoposto a sorveglianza, il prossimo sara\' un ban.'
                    channel = await member.create_dm()
                    sharedFunctions.update_json_file(prev_dict, 'aflers.json')
                    await channel.send('Sei stato ' + penalty + ' Motivo: ' + reason + '.')
                elif d["violations_count"] >= 4:
                    penalty = 'bannato dal server.' 
                    channel = await member.create_dm()
                    await channel.send('Sei stato ' + penalty + ' Motivo: ' + reason + '.')
                    sharedFunctions.update_json_file(prev_dict, 'aflers.json')
                    await member.ban(delete_message_days = 0, reason = reason)   
                else:
                    channel = await member.create_dm()
                    sharedFunctions.update_json_file(prev_dict, 'aflers.json')
                    await channel.send('Sei stato ' + penalty + ' Motivo: ' + reason + '.')
            else:
                #contatore per ogni giorno per ovviare i problemi discussi nella issue #2
                if number < 0:
                    return
                afler = {
                    "mon": 0,
                    "tue": 0,
                    "wed": 0,
                    "thu": 0,
                    "fri": 0,
                    "sat": 0,
                    "sun": 0,
                    "counter": 0,
                    "last_message_date": None,
                    "violations_count": number,
                    "last_violation_count": datetime.date(datetime.now()).__str__(),
                    "active": False,
                    "expiration": None
                }
                prev_dict[key] = afler
                sharedFunctions.update_json_file(prev_dict, 'aflers.json')

def setup(bot):
    try:
        with open('config.json', 'r') as file:
            config = json.load(file)
    except FileNotFoundError:
        print('crea il file config.json seguendo le indicazioni del template')
        exit()
    bot.add_cog(ModerationCog(bot, config))