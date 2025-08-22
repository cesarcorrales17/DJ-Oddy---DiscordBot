import discord 
from discord.ext import commands
from dotenv import load_dotenv
import os
import yt_dlp
import asyncio

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()  # Intents: permisos que el bot tiene para recibir eventos de Discord
intents.message_content = True  # Permiso para leer el contenido de los mensajes
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)  # Desactivar help automático, Definimos el bot con el prefijo (!)

# Variables globales para manejar la música
voice_clients = {}  # Para almacenar las conexiones de voz por servidor
queues = {}         # Para almacenar las colas de música por servidor

# Configuración de yt-dlp para extraer audio
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch1',  # Busca en YouTube si no es URL
    'source_address': '0.0.0.0',
    'cachedir': False,
}


# Configuración para reproducción en Discord
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'  # Sin video, solo audio
}

# Crear el extractor de yt-dlp
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# Evento que ejecuta el bot cuando se conecta
@bot.event
async def on_ready():
    print(f"Estoy listo para el perreo {bot.user}")

# Función para extraer información de YouTube
async def get_song_info(query):
    try:
        # Extraer información del video sin descargarlo
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        
        if 'entries' in data:
            # Si es una búsqueda, tomar el primer resultado
            data = data['entries'][0]
        
        # Retornar la información necesaria
        return {
            'title': data['title'],
            'url': data['url'],
            'webpage_url': data['webpage_url']
        }
    except Exception as e:
        print(f"Error al extraer info: {e}")
        return None

@bot.command(name='play')
async def play(ctx, *, query):
    # Verificar si el usuario está en un canal de voz
    if not ctx.author.voice:
        await ctx.send("❌ Debes estar en un canal de voz para usar este comando.")
        return
    
    # Obtener el canal de voz del usuario
    channel = ctx.author.voice.channel
    
    # Conectar el bot al canal de voz
    voice_client = None
    if ctx.guild.voice_client is None:
        # Si el bot no está conectado, se conecta
        voice_client = await channel.connect()
        voice_clients[ctx.guild.id] = voice_client
        await ctx.send(f"🔊 Conectado a **{channel.name}**")
    else:
        # Si ya está conectado, usa la conexión existente
        voice_client = ctx.guild.voice_client
    
    # Mostrar mensaje de búsqueda
    await ctx.send(f"🔍 Buscando: **{query}**...")

    # Extraer información de la canción
    song_info = await get_song_info(query)

    if song_info is None:
        await ctx.send("❌ No se pudo encontrar la canción.")
        return

    # Inicializar la cola del servidor si no existe
    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = []
    
    # Función para reproducir la siguiente canción en la cola
    def play_next(error=None):
        if error:
            print(f"Error en la reproducción: {error}")
        
        # Verificar si hay más canciones en la cola
        if ctx.guild.id in queues and queues[ctx.guild.id]:
            # Obtener la siguiente canción
            next_song = queues[ctx.guild.id].pop(0)
            
            # Crear el reproductor de audio
            next_audio = discord.FFmpegPCMAudio(
                next_song['url'],
                executable=r"E:\PROYECTOS\ffmpeg-7.0.2-essentials_build\bin\ffmpeg.exe",
                **ffmpeg_options
            )
            
            # Reproducir la siguiente canción
            voice_client = voice_clients.get(ctx.guild.id)
            if voice_client:
                voice_client.play(next_audio, after=play_next)
                asyncio.run_coroutine_threadsafe(
                    ctx.send(f"🎶 Reproduciendo ahora: **{next_song['title']}**"),
                    bot.loop
                )
    
    # Agregar la canción a la cola
    queues[ctx.guild.id].append(song_info)
    
    # Si no está reproduciendo, comenzar a reproducir
    if not voice_client.is_playing():
        # Obtener la primera canción de la cola
        current_song = queues[ctx.guild.id].pop(0)
        
        # Crear el reproductor de audio
        audio_source = discord.FFmpegPCMAudio(
            current_song['url'],
            executable=r"E:\PROYECTOS\ffmpeg-7.0.2-essentials_build\bin\ffmpeg.exe",
            **ffmpeg_options
        )
        
        # Reproducir la música con callback para la siguiente canción
        voice_client.play(audio_source, after=play_next)
        await ctx.send(f"🎶 Reproduciendo: **{current_song['title']}**")
    else:
        # Si ya está reproduciendo, informar que se agregó a la cola
        await ctx.send(f"📋 Añadido a la cola: **{song_info['title']}**")

@bot.command(name='stop')
async def stop(ctx):
    # Verificar si el bot está conectado a un canal de voz
    if ctx.guild.voice_client is None:
        await ctx.send("❌ No estoy reproduciendo música.")
        return
    
    # Detener la reproducción y desconectar
    voice_client = ctx.guild.voice_client
    
    # Limpiar las variables del servidor antes de detener
    if ctx.guild.id in queues:
        queues[ctx.guild.id] = []
    
    voice_client.stop()  # Detener la música actual
    await voice_client.disconnect()  # Desconectar del canal
    
    # Limpiar la referencia a la conexión de voz
    if ctx.guild.id in voice_clients:
        del voice_clients[ctx.guild.id]
    
    await ctx.send("⏹️ Música detenida y bot desconectado.")

@bot.command(name='skip')
async def skip(ctx):
    # Verificar si el bot está conectado y reproduciendo
    if ctx.guild.voice_client is None:
        await ctx.send("❌ No estoy reproduciendo música.")
        return
    
    voice_client = ctx.guild.voice_client
    
    # Verificar si hay música reproduciéndose
    if not voice_client.is_playing():
        await ctx.send("❌ No hay música reproduciéndose actualmente.")
        return
    
    # Verificar si hay más canciones en la cola
    if ctx.guild.id in queues and queues[ctx.guild.id]:
        await ctx.send(f"⏭️ Saltando a la siguiente canción...")
    else:
        await ctx.send("⏭️ Canción omitida. No hay más canciones en la cola.")
    
    # Detener la canción actual (esto activará el callback que reproducirá la siguiente)
    voice_client.stop()

@bot.command(name='queue')
async def queue(ctx):
    # Verificar si existe una cola para este servidor
    if ctx.guild.id not in queues or not queues[ctx.guild.id]:
        await ctx.send("📋 La cola está vacía.")
        return
    
    # Construir el mensaje de la cola
    queue_list = queues[ctx.guild.id]
    message = "📋 **Cola de canciones:**\n"
    
    # Mostrar las próximas 10 canciones
    for i, song in enumerate(queue_list[:10], 1):
        message += f"{i}. {song['title']}\n"
    
    # Si hay más de 10 canciones
    if len(queue_list) > 10:
        message += f"... y {len(queue_list) - 10} más."
    
    await ctx.send(message)

@bot.command(name='nowplaying', aliases=['np', 'current'])
async def now_playing(ctx):
    # Verificar si el bot está reproduciendo música
    if ctx.guild.voice_client is None or not ctx.guild.voice_client.is_playing():
        await ctx.send("❌ No estoy reproduciendo música actualmente.")
        return
    
    # Verificamos si hay una canción en reproducción
    # La canción actual no está en la cola, por lo que no podemos obtener su título directamente
    # Podemos mantener un seguimiento de la canción actual en una variable global
    
    # Por ahora, simplemente informamos que hay música reproduciéndose
    await ctx.send("🎵 Hay una canción reproduciéndose actualmente.")
    
    # Si hay canciones en cola, mostrar la próxima
    if ctx.guild.id in queues and queues[ctx.guild.id]:
        next_song = queues[ctx.guild.id][0]
        await ctx.send(f"⏭️ Siguiente en la cola: **{next_song['title']}**")

@bot.command(name='help')
async def help_command(ctx):
    # Crear embed para mejor presentación
    embed = discord.Embed(
        title="🎵 DJ Oddy - Comandos de Música",
        description="¡Aquí tienes todos los comandos disponibles!",
        color=0x00ff00  # Color verde
    )
    
    # Agregar campos con información de cada comando
    embed.add_field(
        name="🎶 !play [canción/URL]", 
        value="Reproduce música desde YouTube\n`!play nombre cancion` o `!play https://youtu.be/...`", 
        inline=False
    )
    embed.add_field(
        name="⏹️ !stop", 
        value="Detiene la música y desconecta el bot", 
        inline=False
    )
    embed.add_field(
        name="⏭️ !skip", 
        value="Salta a la siguiente canción de la cola", 
        inline=False
    )
    embed.add_field(
        name="📋 !queue", 
        value="Muestra las canciones en cola", 
        inline=False
    )
    embed.add_field(
        name="🎵 !np o !nowplaying", 
        value="Muestra la canción que se está reproduciendo actualmente", 
        inline=False
    )
    embed.add_field(
        name="❓ !help", 
        value="Muestra este mensaje de ayuda", 
        inline=False
    )
    
    await ctx.send(embed=embed)
    
    await ctx.send(embed=embed)
    
# Arranque del bot con el token
bot.run(TOKEN)