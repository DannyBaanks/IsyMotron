#include <jni.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include "GUSLlamaBridge.h"

static void throw_state(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(env, "java/lang/IllegalStateException");
    if (type != NULL) (*env)->ThrowNew(env, type, message == NULL ? "GUS native runtime error" : message);
}

JNIEXPORT jlong JNICALL Java_io_github_dannybaanks_isymotron_GusLocalPlugin_nativeCreate(
        JNIEnv *env, jclass type, jstring model_path, jint context_tokens) {
    (void)type;
    if (model_path == NULL || context_tokens < 512 || context_tokens > 2048) {
        throw_state(env, "Invalid GUS model path or context limit."); return 0;
    }
    const char *path = (*env)->GetStringUTFChars(env, model_path, NULL);
    if (path == NULL) return 0;
    char error[512] = {0};
    GUSLlamaContext *context = gus_llama_create(path, (uint32_t)context_tokens, error, sizeof(error));
    (*env)->ReleaseStringUTFChars(env, model_path, path);
    if (context == NULL) throw_state(env, error);
    return (jlong)(intptr_t)context;
}

JNIEXPORT jstring JNICALL Java_io_github_dannybaanks_isymotron_GusLocalPlugin_nativeGenerate(
        JNIEnv *env, jclass type, jlong handle, jobjectArray roles, jobjectArray contents, jint max_tokens) {
    (void)type;
    if (handle == 0 || roles == NULL || contents == NULL || max_tokens < 1 || max_tokens > 160) {
        throw_state(env, "Invalid GUS generation limit."); return NULL;
    }
    jsize count = (*env)->GetArrayLength(env, roles);
    if (count == 0 || count > 64 || (*env)->GetArrayLength(env, contents) != count) {
        throw_state(env, "Invalid GUS message count."); return NULL;
    }
    GUSChatMessage *messages = calloc((size_t)count, sizeof(GUSChatMessage));
    jstring *role_refs = calloc((size_t)count, sizeof(jstring));
    jstring *content_refs = calloc((size_t)count, sizeof(jstring));
    if (messages == NULL || role_refs == NULL || content_refs == NULL) {
        free(messages); free(role_refs); free(content_refs); throw_state(env, "GUS message allocation failed."); return NULL;
    }
    bool valid = true;
    size_t total_chars = 0;
    for (jsize i = 0; i < count; i++) {
        role_refs[i] = (jstring)(*env)->GetObjectArrayElement(env, roles, i);
        content_refs[i] = (jstring)(*env)->GetObjectArrayElement(env, contents, i);
        messages[i].role = (*env)->GetStringUTFChars(env, role_refs[i], NULL);
        messages[i].content = (*env)->GetStringUTFChars(env, content_refs[i], NULL);
        if (messages[i].role == NULL || messages[i].content == NULL) { valid = false; break; }
        if (strcmp(messages[i].role, "system") && strcmp(messages[i].role, "user") && strcmp(messages[i].role, "assistant")) valid = false;
        size_t size = strlen(messages[i].content); total_chars += size;
        if (size > 12000 || total_chars > 32000) valid = false;
    }
    if (!valid) {
        for (jsize i = 0; i < count; i++) {
            if (messages[i].role != NULL) (*env)->ReleaseStringUTFChars(env, role_refs[i], messages[i].role);
            if (messages[i].content != NULL) (*env)->ReleaseStringUTFChars(env, content_refs[i], messages[i].content);
            if (role_refs[i] != NULL) (*env)->DeleteLocalRef(env, role_refs[i]);
            if (content_refs[i] != NULL) (*env)->DeleteLocalRef(env, content_refs[i]);
        }
        free(messages); free(role_refs); free(content_refs); throw_state(env, "Invalid or oversized GUS message."); return NULL;
    }
    GUSGenerationStats stats = {0}; char error[512] = {0};
    GUSSamplingParams sampling = gus_llama_default_chat_sampling();
    char *text = gus_llama_generate_chat_sampled((GUSLlamaContext *)(intptr_t)handle, messages, (size_t)count, NULL,
                                                  (uint32_t)max_tokens, &sampling, &stats, error, sizeof(error));
    for (jsize i = 0; i < count; i++) {
        (*env)->ReleaseStringUTFChars(env, role_refs[i], messages[i].role);
        (*env)->ReleaseStringUTFChars(env, content_refs[i], messages[i].content);
        (*env)->DeleteLocalRef(env, role_refs[i]); (*env)->DeleteLocalRef(env, content_refs[i]);
    }
    free(messages); free(role_refs); free(content_refs);
    if (text == NULL) { throw_state(env, error); return NULL; }
    jstring result = (*env)->NewStringUTF(env, text); gus_llama_free_text(text); return result;
}

JNIEXPORT void JNICALL Java_io_github_dannybaanks_isymotron_GusLocalPlugin_nativeCancel(JNIEnv *env, jclass type, jlong handle) {
    (void)env; (void)type; if (handle != 0) gus_llama_cancel((GUSLlamaContext *)(intptr_t)handle);
}
JNIEXPORT void JNICALL Java_io_github_dannybaanks_isymotron_GusLocalPlugin_nativeDestroy(JNIEnv *env, jclass type, jlong handle) {
    (void)env; (void)type; if (handle != 0) gus_llama_destroy((GUSLlamaContext *)(intptr_t)handle);
}
