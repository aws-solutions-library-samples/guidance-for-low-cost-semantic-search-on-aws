$(document).ready(function () {
    let fileinput = $("#file-upload");
    const $fileList = $('.file-list');
    let displayDocuments = $("#display-docs");
    let uploadFile = $("#upload-btn");
    
    // Map to track upload progress of each file
    const uploadProgressMap = new Map();
    
    // Create file item for upload using DOM methods instead of innerHTML
    function UIuploadFile(file) {
        const fileId = 'file-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        
        // Clone the file item template
        const template = document.getElementById('file-item-template');
        const fileItem = document.importNode(template.content.firstElementChild, true);
        
        // Set file ID and name
        fileItem.id = fileId;
        const fileNameElement = fileItem.querySelector('.file-name');
        fileNameElement.textContent = file.name;
        
        // Append to file list
        $fileList.append(fileItem);
        uploadProgressMap.set(fileId, 0);
        
        return { fileItem, fileId };
    }
    
    // Update progress for a file
    function updateProgress(fileId, progress) {
        const fileItem = document.getElementById(fileId);
        if (!fileItem) return;
        
        const progressBar = fileItem.querySelector('.progress');
        progressBar.style.width = `${progress}%`;
        uploadProgressMap.set(fileId, progress);
        
        if (progress >= 100) {
            setTimeout(() => {
                const progressBarContainer = fileItem.querySelector('.progress-bar');
                if (progressBarContainer) {
                    // Fade out
                    progressBarContainer.style.opacity = '0';
                    setTimeout(() => {
                        // Remove progress bar
                        if (progressBarContainer.parentNode) {
                            progressBarContainer.parentNode.removeChild(progressBarContainer);
                            
                            // Add delete button
                            if (!fileItem.querySelector('.delete-btn')) {
                                const deleteBtn = document.createElement('button');
                                deleteBtn.className = 'delete-btn';
                                
                                const icon = document.createElement('i');
                                icon.className = 'fas fa-trash';
                                deleteBtn.appendChild(icon);
                                
                                deleteBtn.addEventListener('click', deleteFile);
                                fileItem.appendChild(deleteBtn);
                            }
                        }
                    }, 300);
                }
            }, 500);
        }
    }
    
    // Delete file handler
    function deleteFile(event) {
        const fileItem = event.target.closest('.file-item');
        const group = fileItem.querySelector('.list-file-key').textContent;
        const filename = fileItem.querySelector('.file-name').textContent;
        
        // Show confirmation dialog
        showConfirmation(
            `Are you sure you want to delete <strong>${filename}</strong>?`,
            function() {
                // Confirm delete
                let apiendpointdocuments = $("#apiendpointdocuments").text();
                fileItem.classList.add('fade-out');
                
                setTimeout(() => {
                    del(apiendpointdocuments, { group: group, filename: filename })
                        .then(function() {
                            if (fileItem.parentNode) {
                                fileItem.parentNode.removeChild(fileItem);
                            }
                            showSuccessNotification(`File "${filename}" was successfully deleted.`);
                        })
                        .catch(function(error) {
                            console.error('Error deleting file:', error);
                            showErrorNotification(`Failed to delete file "${filename}". Please try again.`);
                            fileItem.classList.remove('fade-out');
                        });
                }, 300);
            }
        );
    }
    
    // Add file to the document list
    function addFile(file) {
        // Clone the file list item template
        const template = document.getElementById('file-list-item-template');
        const fileItem = document.importNode(template.content.firstElementChild, true);
        
        // Set file properties
        fileItem.querySelector('.file-name').textContent = file.filename;
        fileItem.querySelector('.list-file-key').textContent = file.group;
        fileItem.querySelector('.file-size').textContent = formatFileSize(file.size);
        
        // Add event listener to delete button
        const deleteBtn = fileItem.querySelector('.delete-btn');
        deleteBtn.addEventListener('click', deleteFile);
        
        // Append to file list
        $fileList.append(fileItem);
    }
    
    // Format file size in KB, MB, etc.
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // Handle showing/hiding file list
    function displayDocs() {
        if ($fileList.hasClass('hidden')) {
            $fileList.removeClass('hidden');
            
            // Update button text safely
            displayDocuments.empty();
            
            const icon = document.createElement('i');
            icon.className = 'fas fa-folder-close';
            displayDocuments.append(icon);
            
            displayDocuments.append(' Hide Documents');
            
            getDocuments();
        } else {
            $fileList.addClass('hidden');
            
            // Update button text safely
            displayDocuments.empty();
            
            const icon = document.createElement('i');
            icon.className = 'fas fa-folder-open';
            displayDocuments.append(icon);
            
            displayDocuments.append(' Browse Documents');
            
            $fileList.empty();
        }
    }
    
    // Get documents from API
    function getDocuments() {
        // Show loading indicator
        $fileList.empty();
        
        const loadingIndicator = document.createElement('div');
        loadingIndicator.className = 'loading-indicator';
        
        const spinner = document.createElement('i');
        spinner.className = 'fas fa-spinner fa-spin';
        loadingIndicator.appendChild(spinner);
        
        loadingIndicator.appendChild(document.createTextNode(' Loading documents...'));
        $fileList.append(loadingIndicator);
        
        let apiendpointdocuments = $("#apiendpointdocuments").text();
        get(apiendpointdocuments)
            .then(function (data) {
                $fileList.empty();
                
                if (data.length === 0) {
                    const noDocsMessage = document.createElement('div');
                    noDocsMessage.className = 'text-center';
                    noDocsMessage.textContent = 'No documents found';
                    $fileList.append(noDocsMessage);
                    return;
                }
                
                // Sort files by name
                data.sort((a, b) => a.filename.localeCompare(b.filename));
                
                // Add file items
                for (let i = 0; i < data.length; i++) {
                    addFile(data[i]);
                }
            })
            .catch(function(error) {
                console.error('Error fetching documents:', error);
                
                $fileList.empty();
                const errorMessage = document.createElement('div');
                errorMessage.className = 'text-center text-error';
                errorMessage.textContent = 'Failed to load documents';
                $fileList.append(errorMessage);
                
                showErrorNotification('Failed to load documents. Please try again.');
            });
    }
    
    // Check file size and type
    function validateFile(file) {
        const maxSizeInBytes = 1024 * 1024 * 10; // 10 MB
        const allowedTypes = ['.pdf'];
        
        // Check file size
        if (file.size > maxSizeInBytes) {
            showWarningNotification(`"${file.name}" exceeds the 10MB size limit.`, 5000);
            return false;
        }
        
        // Check file type
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
        if (!allowedTypes.includes(fileExtension)) {
            showWarningNotification(`"${file.name}" is not a PDF file. Only PDF files are supported.`, 5000);
            return false;
        }
        
        return true;
    }
    
    // Handle file selection
    function validateFiles() {
        const validFiles = [];
        
        for (let i = 0; i < this.files.length; i++) {
            if (validateFile(this.files[i])) {
                validFiles.push(this.files[i]);
            }
        }
        
        // Update file input label with count of selected files
        const fileInputLabel = document.querySelector('.file-input-label');
        
        if (validFiles.length > 0) {
            fileInputLabel.textContent = `${validFiles.length} file(s) selected`;
        } else {
            // Reset label
            fileInputLabel.innerHTML = '';
            
            const icon = document.createElement('i');
            icon.className = 'fas fa-file-pdf';
            fileInputLabel.appendChild(icon);
            
            fileInputLabel.appendChild(document.createTextNode(' Choose PDF files'));
        }
    }
    
    // Upload files
    function uploadFiles() {
        let files = $("#file-upload")[0].files;
        
        if (files.length === 0) {
            showWarningNotification('Please select a file to upload', 3000, true);
            return;
        }
        
        // Show documents list if it's hidden
        if ($fileList.hasClass('hidden')) {
            displayDocuments.click();
        }
        
        let apiendpoint = $("#apiendpointupload").text();
        let validFilesCount = 0;
        
        // Track successful uploads
        let successfulUploads = 0;
        let failedUploads = 0;
        
        for (let i = 0; i < files.length; i++) {
            if (!validateFile(files[i])) continue;
            
            validFilesCount++;
            const { fileItem, fileId } = UIuploadFile(files[i]);
            
            // Get presigned URL
            get(apiendpoint + "?file_name=" + files[i].name)
                .then(response => {
                    updateProgress(fileId, 20);
                    
                    // Upload to presigned URL
                    return put(response["url"], files[i])
                        .then(() => {
                            updateProgress(fileId, 100);
                            successfulUploads++;
                            
                            // Show notification if all uploads are complete
                            if (successfulUploads + failedUploads === validFilesCount) {
                                if (failedUploads === 0) {
                                    showSuccessNotification(`${successfulUploads} file(s) uploaded successfully`, 3000);
                                } else {
                                    showWarningNotification(`${successfulUploads} file(s) uploaded, ${failedUploads} failed`, 3000);
                                }
                                
                                // Reset file input
                                $("#file-upload").val('');
                                
                                // Reset file input label
                                const fileInputLabel = document.querySelector('.file-input-label');
                                fileInputLabel.innerHTML = '';
                                
                                const icon = document.createElement('i');
                                icon.className = 'fas fa-file-pdf';
                                fileInputLabel.appendChild(icon);
                                
                                fileInputLabel.appendChild(document.createTextNode(' Choose PDF files'));
                                
                                // Refresh document list
                                setTimeout(getDocuments, 1000);
                            }
                        });
                })
                .catch(error => {
                    console.error('Error uploading file:', error);
                    
                    // Mark file item as error
                    const fileItemElem = document.getElementById(fileId);
                    if (fileItemElem) {
                        fileItemElem.classList.add('error');
                        
                        // Remove progress bar
                        const progressBar = fileItemElem.querySelector('.progress-bar');
                        if (progressBar && progressBar.parentNode) {
                            progressBar.parentNode.removeChild(progressBar);
                        }
                        
                        // Add error message
                        const errorMsg = document.createElement('div');
                        errorMsg.className = 'error-message';
                        errorMsg.textContent = 'Upload failed';
                        fileItemElem.appendChild(errorMsg);
                    }
                    
                    failedUploads++;
                    
                    // Show notification if all uploads are complete
                    if (successfulUploads + failedUploads === validFilesCount) {
                        if (successfulUploads === 0) {
                            showErrorNotification('All file uploads failed. Please try again.', 3000);
                        } else {
                            showWarningNotification(`${successfulUploads} file(s) uploaded, ${failedUploads} failed`, 3000);
                        }
                    }
                });
        }
    }
    
    // Event listeners
    fileinput.on('change', validateFiles);
    uploadFile.click(uploadFiles);
    displayDocuments.click(displayDocs);
    
    // Initialize UI - show document count badge if available
    if ($("#apiendpointdocuments").text() === "") {
        // wait
        setTimeout(function () {
            get($("#apiendpointdocuments").text())
                .then(function (data) {
                    if (data && data.length > 0) {
                        // Update display docs button with count
                        displayDocuments.empty();
                        
                        const icon = document.createElement('i');
                        icon.className = 'fas fa-folder-open';
                        displayDocuments.append(icon);
                        
                        displayDocuments.append(' Browse Docs ');
                        
                        const badge = document.createElement('span');
                        badge.className = 'badge';
                        badge.textContent = data.length;
                        displayDocuments.append(badge);
                    }
                })
                .catch(function (err) {
                    console.error('Error fetching document count:', err);
                });

        }, 1000);
    }
    
});
